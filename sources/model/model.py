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
        self.__uri          : str  = uri
        self.__model        : str  = model
        self.__tools_support: bool = self.__probe(uri, model)

    @property
    def model(self) -> str:
        """ Get the current model """
        return self.__model

    @staticmethod
    def __probe(uri: str, model: str) -> bool:
        """ Check a model is available, and tell whether it can call tools """
        try:
            res = requests.post(f"{uri}/api/show", json={"model": model}, timeout=5.0)
        except requests.RequestException:
            raise ModelException(f"Cannot reach {uri}")
        if res.status_code != 200:
            raise ModelException(f"Unknown model {model}")
        # Older Ollama versions don't report capabilities: assume tools work
        capabilities: list[str] | None = res.json().get("capabilities")
        return capabilities is None or "tools" in capabilities

    def switch(self, *, newuri: str | None = None, newmodel: str | None = None) -> None:
        """ Switch model, the current one is kept if the new one is not available """
        uri  : str = newuri or self.__uri
        model: str = newmodel or self.__model
        tools_support: bool = self.__probe(uri, model)
        self.__uri, self.__model, self.__tools_support = uri, model, tools_support

    def chat(
            self,
            messages: list[dict],
            tools: list[dict] | None = None,
            *,
            on_text: Callable[[str], None] | None = None
        ) -> Reply:
        """ Send a conversation to the model, streaming its text through on_text if given """
        payload: dict = {
            "model": self.__model,
            "messages": messages,
            "stream": on_text is not None,
        }
        if tools and self.__tools_support:
            payload["tools"] = tools

        reply: Reply = Reply()
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
                        if on_text is not None:
                            on_text(text)
                    # Tool calls can be spread over several chunks: collect them all
                    reply.tool_calls += [
                        ToolCall.from_dict(call) for call in message.get("tool_calls") or []
                    ]
                res.raise_for_status()
        except requests.RequestException as e:
            raise ModelException(f"Model request failed: {e}") from e
        except json.JSONDecodeError as e:
            raise ModelException(f"Bad response from model: {e}") from e
        return reply
