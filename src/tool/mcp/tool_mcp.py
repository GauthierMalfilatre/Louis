##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## MCP tool: a tool of an MCP server, offered to the model as <server>__<tool>, run through call_tool
##
from tool.tool import Tool
from tool.risk import Risk, NONE, SAFE, REVERSIBLE, IRREVERSIBLE
from tool.mcp.client import McpClient, McpError, McpTimeout
from tool.mcp.config import risk_of
from events.event_list import MCP_PROGRESS
import json
import re
import time

# What the name of a tool may hold for the model (Ollama, as the API of OpenAI): the rest becomes _
UNNAMED: re.Pattern = re.compile(r"[^A-Za-z0-9_-]")
MAX_NAME: int = 64

# Seconds between two steps of a long call told to the user, unless the server says something new
PROGRESS_EVERY: float = 0.5

def tool_name(server: str, tool: str) -> str:
    """ The name the model calls a tool of a server by: <server>__<tool> """
    return f"{UNNAMED.sub('_', server)}__{UNNAMED.sub('_', tool)}"[:MAX_NAME]

def prompt_name(server: str, prompt: str) -> str:
    """ The command the user runs a prompt of a server with: /<server>:<prompt> """
    return f"{UNNAMED.sub('_', server)}:{UNNAMED.sub('_', prompt)}"

def text_of(result: dict) -> str:
    """
        What a tool of a server gave, as the model reads it: its texts, what it can not read (an image) named only.
        Its structured content when it gave no text
    """
    parts: list[str] = []
    for item in result.get("content") or []:
        if not isinstance(item, dict):
            continue
        match item.get("type"):
            case "text":
                parts.append(item.get("text") or "")
            case "image" | "audio":
                parts.append(f"[{item['type']} {item.get('mimeType', '')}]".replace(" ]", "]"))
            case "resource":
                resource: dict = item.get("resource") or {}
                parts.append(resource.get("text") or f"[ressource {resource.get('uri', '')}]")
            case "resource_link":
                parts.append(f"[ressource {item.get('uri', '')}] {item.get('name', '')}".rstrip())
    text: str = "\n".join(part for part in parts if part)
    if not text and result.get("structuredContent") is not None:
        text = json.dumps(result["structuredContent"], ensure_ascii=False)
    return text

class McpTool(Tool):
    """
        A tool of an MCP server. Its risk is what the settings of its server say of it, else what the server says of it
        (its annotations): one that only reads asks nothing, the others ask before they act, and join the plan.
        It calls the server as it is now: one started again since the tool was made is called all the same
    """
    def __init__(self, server, spec: dict):
        """
            Init the tool of the server (an McpServer: its name, its risk, its timeout, connect()) from what
            tools/list gave of it
        """
        parameters: dict = {key: value for key, value in (spec.get("inputSchema") or {}).items() if key != "$schema"}
        parameters.setdefault("type", "object")
        if parameters["type"] == "object":
            parameters.setdefault("properties", {})
        self.__about: str = (spec.get("description") or spec.get("title") or "").strip()
        super().__init__(tool_name(server.name, spec["name"]), f"[MCP {server.name}] {self.__about}".rstrip(), parameters)
        self.__server     : str        = server.name
        self.__host                    = server
        self.__remote     : str        = spec["name"]
        self.__level      : str | None = risk_of(server.level, spec["name"])
        self.__annotations: dict       = spec.get("annotations") or {}

    @property
    def server(self) -> str:
        """ Get the name of the server of the tool """
        return self.__server

    @property
    def remote(self) -> str:
        """ Get the name of the tool on its server """
        return self.__remote

    @property
    def about(self) -> str:
        """ Get what the server says the tool does """
        return self.__about

    @property
    def level(self) -> str:
        """
            How risky any call of the tool is: what the settings of its server say, else what the server says of it.
            One that does not say it only reads, nor that it destroys nothing, can not be undone: a risk that is not
            known is never taken for none
        """
        if self.__level is not None:
            return self.__level
        if self.__annotations.get("readOnlyHint") is True:
            return SAFE
        if self.__annotations.get("destructiveHint") is False:
            return REVERSIBLE
        return IRREVERSIBLE

    def risk(self, app, **kwargs) -> Risk:
        """ What the call would do: what the tool acts on is only known by its server, its arguments are shown """
        level: str = self.level
        if level == SAFE:
            return NONE
        preview: str = json.dumps(kwargs, ensure_ascii=False, indent=2)
        if level == REVERSIBLE:
            return Risk(REVERSIBLE, f"{self.__remote} du serveur MCP {self.__server} agira, sans rien détruire d'après "
                                    "lui", preview=preview)
        return Risk(IRREVERSIBLE, f"{self.__remote} du serveur MCP {self.__server} agira hors de Louis : ni ce qu'il "
                                  "change ni comment l'annuler ne sont connus", preview=preview)

    def __progress(self, app):
        """
            What tells the user how far a long call is: a step every PROGRESS_EVERY seconds at most, or as soon as
            the server says something new
        """
        last: dict = {"at": 0.0, "message": None}
        def told(step: dict) -> None:
            now: float = time.monotonic()
            message = step.get("message")
            if now - last["at"] < PROGRESS_EVERY and message == last["message"]:
                return
            last.update(at=now, message=message)
            app.events.dispatch(MCP_PROGRESS, tool=self.name, server=self.__server, progress=step.get("progress"),
                                total=step.get("total"), message=message)
        return told

    def handle(self, app, **kwargs) -> str:
        """ Call the tool on its server, once allowed: whatever goes wrong there comes back as an error, never raised """
        if self.level != SAFE and not app.permissions.request(
            self.name, f"Appel de {self.__remote} sur le serveur MCP {self.__server}", self.risk(app, **kwargs).preview
        ):
            return (f"Refusé : l'utilisateur n'a pas autorisé l'appel de '{self.name}'. "
                    "Ne le retente pas : demande-lui ce qu'il veut à la place.")
        client: McpClient | None = self.__host.connect()
        if client is None or not client.alive:
            return (f"Erreur : le serveur MCP {self.__server} ne répond plus : {self.__host.why}. "
                    "Fais sans cet outil ; l'utilisateur voit son état avec /mcp.")
        try:
            result: dict = client.call_tool(self.__remote, kwargs, self.__host.timeout, self.__progress(app),
                                            self.__host.max_timeout)
        except McpTimeout as e:
            return (f"Erreur : le serveur MCP {self.__server} n'a pas répondu à {self.__remote} en "
                    f"{round(e.waited, 1):g} s. Fais autrement, ou réessaie plus tard.")
        except McpError as e:
            if client.crashed:
                # Never called again by itself: the call may have acted before the crash
                after: str = "Il sera relancé au prochain appel" if self.__host.restarts > 0 else \
                    "Fais sans cet outil ; l'utilisateur voit son état avec /mcp"
                return (f"Erreur : le serveur MCP {self.__server} s'est arrêté pendant {self.__remote} ({e}) : "
                        f"ce qu'il a fait avant n'est pas connu. {after}.")
            return f"Erreur : le serveur MCP {self.__server} n'a pas pu lancer {self.__remote} : {e}."
        text: str = text_of(result)
        if result.get("isError"):
            return f"Erreur : {text or f'{self.__remote} a échoué sans dire pourquoi.'}"
        return text or f"{self.__remote} n'a rien renvoyé."
