##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /<server>:<prompt>: a prompt of an MCP server, written by the server with the arguments typed, then answered by
## the model as a message of the user
##
from command.command import Command
from events.event_list import MCP_PROMPT
from tool.mcp.client import McpError
from tool.mcp.tool_mcp import prompt_name, text_of
import shlex

class McpPromptCommand(Command):
    """
        A prompt of an MCP server. What the server writes comes from outside of Louis: it is sent as one message of
        the user, checked by the guard as any other
    """
    def __init__(self, server, spec: dict):
        """ Init the command of the prompt of the server (an McpServer), as prompts/list gave it """
        self.__server   = server
        self.__remote   : str        = spec["name"]
        self.__arguments: list[dict] = [argument for argument in spec.get("arguments") or []
                                        if isinstance(argument, dict) and isinstance(argument.get("name"), str)]
        about: str = (spec.get("description") or spec.get("title") or "").strip()
        usage: str = " ".join(f"<{argument['name']}>" if argument.get("required") else f"[{argument['name']}]"
                              for argument in self.__arguments)
        super().__init__(prompt_name(server.name, self.__remote), description=f"[MCP {server.name}] {about}".rstrip(),
                         usage=usage)

    @property
    def server(self) -> str:
        """ Get the name of the server of the prompt """
        return self.__server.name

    def handle(self, app, arguments: str) -> None:
        """ Ask the server for the prompt, written with the arguments typed, and answer it as a message of the user """
        try:
            values: dict[str, str] = self.values(arguments)
        except ValueError as e:
            self.error(app, "usage", f"{e} Usage : /{self.name} {self.usage}".rstrip())
            return
        client = self.__server.connect()
        if client is None or not client.alive:
            self.error(app, "unavailable", f"Le serveur MCP {self.server} ne répond plus : {self.__server.why}.")
            return
        try:
            prompt: dict = client.get_prompt(self.__remote, values, self.__server.timeout)
        except McpError as e:
            self.error(app, "failed", f"Le serveur MCP {self.server} n'a pas donné le prompt {self.__remote} : {e}.")
            return
        text: str = self.text(prompt)
        if not text:
            self.error(app, "empty", f"Le prompt {self.__remote} du serveur MCP {self.server} est vide.")
            return
        app.events.dispatch(MCP_PROMPT, server=self.server, prompt=self.__remote, command=self.name, text=text)
        app.answer(text)

    def values(self, typed: str) -> dict[str, str]:
        """
            The arguments of the prompt, from what the user typed: the whole text for a prompt of one argument; else
            words (in quotes for spaces), name=value or in their order. Raises ValueError with what is wrong
        """
        typed = typed.strip()
        names: list[str] = [argument["name"] for argument in self.__arguments]
        values: dict[str, str] = {}
        if len(names) == 1 and typed:
            values[names[0]] = typed
        elif typed:
            if not names:
                raise ValueError(f"Le prompt {self.__remote} ne prend pas d'argument.")
            try:
                words: list[str] = shlex.split(typed)
            except ValueError:
                raise ValueError("Un guillemet n'est pas fermé.") from None
            positional: list[str] = []
            for word in words:
                key, equal, value = word.partition("=")
                if equal and key in names:
                    values[key] = value
                else:
                    positional.append(word)
            for name in names:
                if name not in values and positional:
                    values[name] = positional.pop(0)
            if positional:
                raise ValueError(f"Trop d'arguments : {' '.join(positional)}.")
        missing: list[str] = [argument["name"] for argument in self.__arguments
                              if argument.get("required") and not values.get(argument["name"])]
        if missing:
            raise ValueError(f"Il manque {', '.join(missing)}.")
        return values

    @staticmethod
    def text(prompt: dict) -> str:
        """
            The messages of the prompt as one message of the user: what the server wrote as the assistant is marked
            so, the model reads it as an example, never as its own words
        """
        parts: list[str] = []
        for message in prompt.get("messages") or []:
            if not isinstance(message, dict):
                continue
            text: str = text_of({"content": [message.get("content")]}).strip()
            if text:
                parts.append(text if message.get("role") != "assistant" else f"(réponse de l'assistant) {text}")
        return "\n\n".join(parts)
