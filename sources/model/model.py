##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Model class def
##
from collections.abc import Callable
from dataclasses import dataclass, field
import json
import requests
from tool.tools import ToolCall

# (connect, read) seconds, the read timeout bounds the silence between two chunks
CHAT_TIMEOUT: tuple[float, float] = (5.0, 600.0)

# Some models (qwen2.5-coder...) write their tool calls as text, with or without these tags
TOOL_CALL_OPEN : str = "<tool_call>"
TOOL_CALL_CLOSE: str = "</tool_call>"

class ModelException(Exception):
    def __init__(self, message: str = "Wrong Model usage"):
        self.message = message
        super().__init__(self.message)

@dataclass
class Reply:
    content   : str            = ""
    tool_calls: list[ToolCall] = field(default_factory=list)

class Model:
    def __init__(self, uri: str, model: str) -> None:
        """ Init model, checking it is available """
        self.__uri         : str      = uri
        self.__model       : str      = model
        self.__capabilities: set[str] = self.__probe(uri, model)

    @property
    def model(self) -> str:
        """ Get the current model """
        return self.__model

    @property
    def vision(self) -> bool:
        """ Whether the model can read the images sent with a message """
        return "vision" in self.__capabilities

    @staticmethod
    def __probe(uri: str, model: str) -> set[str]:
        """ Check a model is available, and get what it is able to do """
        try:
            res = requests.post(f"{uri}/api/show", json={"model": model}, timeout=5.0)
        except requests.RequestException:
            raise ModelException(f"Cannot reach {uri}")
        if res.status_code != 200:
            raise ModelException(f"Unknown model {model}")
        capabilities: list[str] | None = res.json().get("capabilities")
        # Older Ollama versions don't report them: assume the model can do everything
        return set(capabilities) if capabilities is not None else {"tools", "vision"}

    @staticmethod
    def __attach(messages: list[dict], images: list[str]) -> list[dict]:
        """ Put images on the last message of the user, where the model expects them """
        attached: list[dict] = list(messages)
        for index in reversed(range(len(attached))):
            if attached[index].get("role") == "user":
                attached[index] = {
                    **attached[index],
                    "images": [*(attached[index].get("images") or []), *images]
                }
                break
        return attached

    def available(self) -> list[str]:
        """ Get the names of the models the server has """
        try:
            res = requests.get(f"{self.__uri}/api/tags", timeout=5.0)
            res.raise_for_status()
        except requests.RequestException:
            raise ModelException(f"Cannot reach {self.__uri}")
        return sorted(model["name"] for model in res.json().get("models") or [])

    def switch(self, *, newuri: str | None = None, newmodel: str | None = None) -> None:
        """ Switch model, the current one is kept if the new one is not available """
        uri  : str = newuri or self.__uri
        model: str = newmodel or self.__model
        capabilities: set[str] = self.__probe(uri, model)
        self.__uri, self.__model, self.__capabilities = uri, model, capabilities

    def chat(
            self,
            messages: list[dict],
            tools: list[dict] | None = None,
            images: list[str] | None = None,
            *,
            on_text: Callable[[str], None] | None = None
        ) -> Reply:
        """ Send a conversation to the model, streaming its text through on_text if given

            Images are base64 strings, either carried by the messages or given here for the
            last one of the user. A model that cannot see them says so before anything is sent.
        """
        if images:
            messages = self.__attach(messages, images)
        if not self.vision and any(message.get("images") for message in messages):
            current: dict = next(
                (message for message in reversed(messages) if message.get("role") == "user"), {}
            )
            if current.get("images"):
                raise ModelException(f"{self.__model} cannot read images")
            # Pictures from earlier in the session: go on without them rather than block it
            messages = [
                {key: value for key, value in message.items() if key != "images"}
                for message in messages
            ]

        payload: dict = {
            "model": self.__model,
            "messages": messages,
            "stream": on_text is not None,
        }
        if tools and "tools" in self.__capabilities:
            payload["tools"] = tools
        names: set[str] = {tool["function"]["name"] for tool in payload.get("tools") or []}

        reply: Reply = Reply()
        # Length of the content given to on_text, the rest is held while it may be a tool call
        shown: int = 0
        try:
            with requests.post(
                f"{self.__uri}/api/chat", json=payload, stream=True, timeout=CHAT_TIMEOUT
            ) as res:
                # Not streamed, the whole reply is a single line: both modes are read the same way
                for line in res.iter_lines():
                    if not line:
                        continue
                    chunk: dict = json.loads(line)
                    # Ollama sends errors as an {"error": ...} line, as HTTP error body or mid-stream
                    if "error" in chunk:
                        raise ModelException(f"Model error: {chunk['error']}")
                    message: dict = chunk.get("message") or {}
                    if text := message.get("content"):
                        reply.content += text
                        if on_text is not None and not (names and self.__maybe_call(reply.content)):
                            on_text(reply.content[shown:])
                            shown = len(reply.content)
                    # Tool calls can be spread over several chunks: collect them all
                    reply.tool_calls += [
                        ToolCall.from_dict(call) for call in message.get("tool_calls") or []
                    ]
                res.raise_for_status()
        except requests.RequestException as e:
            raise ModelException(f"Model request failed: {e}") from e
        except json.JSONDecodeError as e:
            raise ModelException(f"Bad response from model: {e}") from e

        if names and not reply.tool_calls and (calls := self.__text_calls(reply.content, names)):
            reply.content, reply.tool_calls = "", calls
        if on_text is not None and shown < len(reply.content):
            on_text(reply.content[shown:])
        return reply

    @staticmethod
    def __maybe_call(content: str) -> bool:
        """ Tell whether a reply being streamed may still turn out to be a tool call written as text """
        start: str = content.lstrip()
        return start.startswith("{") or TOOL_CALL_OPEN.startswith(start[:len(TOOL_CALL_OPEN)])

    @staticmethod
    def __text_calls(content: str, names: set[str]) -> list[ToolCall]:
        """ Get the tool calls written as text, if the whole reply is made of calls to known tools """
        decoder: json.JSONDecoder = json.JSONDecoder()
        calls  : list[ToolCall] = []
        text   : str = content.strip()
        while text:
            text = text.removeprefix(TOOL_CALL_OPEN).lstrip()
            try:
                data, end = decoder.raw_decode(text)
            except json.JSONDecodeError:
                return []
            name = data.get("name") if isinstance(data, dict) else None
            # Unknown names are left as text: the model made the tool up
            if not isinstance(name, str) or name not in names:
                return []
            # llama3.2 says "parameters" where the others say "arguments"
            arguments = data.get("arguments", data.get("parameters")) or {}
            if not isinstance(arguments, dict):
                return []
            calls.append(ToolCall(name, arguments))
            text = text[end:].lstrip().removeprefix(TOOL_CALL_CLOSE).lstrip()
        return calls
