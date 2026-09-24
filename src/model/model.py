##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Model Class
##
import requests
from collections.abc import Callable
from .model_exception import ModelException
from .reply import Reply
from config.settings import settings
import json

CHAT_TIMEOUT: tuple[float, float] = (
    settings.get("chat.timeout.connect", 5.0),
    settings.get("chat.timeout.response", 600.0)
)

class OllamaModel:
    """ Model Class, to chat with ollama API """
    def __init__(self, uri: str, model: str) -> "OllamaModel":
        """ Init the model class """
        self.__uri    = uri
        self.__model  = model
        self.__skills = OllamaModel.__probe(uri, model)

    @property
    def model(self) -> str:
        """ Get the model name """
        return self.__model

    @property
    def vision(self) -> bool:
        """ Check if the model can read the images """
        return "vision" in self.__skills

    @property
    def thinking(self) -> bool:
        """ Check if the model has thinking in his capabilites """
        return "thinking" in self.__skills

    @property
    def tools(self) -> bool:
        """ Check if the model has tools in his capabilities """
        return "tools" in self.__skills

    @staticmethod
    def __probe(uri: str, model: str) -> set[str]:
        """ Check model capabilities """
        try:
            res = requests.post(f"{uri}/api/show", json={"model": model}, timeout=5.0)
        except requests.RequestException:
            raise ModelException(f"Cannot reach {uri}")
        if res.status_code != 200:
            raise ModelException(f"Unknown model {model}")
        capabilities: list[str] | None = res.json().get("capabilities")
        return set(capabilities) if capabilities is not None else {"tools", "vision"}

    def chat(self, messages: list[dict], tools: list[dict] = [], images: list[str] = [], *, on_text: Callable | None = None) -> Reply:
        """ Send a conversation to the model, and returning its reply. Images are a list of path """
        payload: dict[str] = {
            "model": self.__model,
            "messages": messages,
            "stream": settings.get("chat.stream", True)
        }

        if tools and self.tools:
            payload["tools"] = tools

        names: set[str] = {tool["function"]["name"] for tool in payload.get("tools") or []}

        reply: Reply = Reply()

        shown: int = 0
        try:
            with requests.post(
                f"{self.__uri}/api/chat", json=payload, stream=settings.get("chat.stream", True), timeout=CHAT_TIMEOUT
            ) as res:
                for line in res.iter_lines():
                    if not line:
                        continue
                    chunk: dict = json.loads(line)
                    if "error" in chunk:
                        raise ModelException(f"Model error: {chunk['error']}")
                    message: dict = chunk.get("message") or {}
                    if text := message.get("content"):
                        reply.content += text
                        if on_text is not None and not (names and self.__maybe_call(reply.content)):
                            on_text(reply.content[shown:])
                            shown = len(reply.content)

                    # TODO: Tools
                    # Tool calls can be spread over several chunks: collect them all
                    # reply.tool_calls += [
                    #     ToolCall.from_dict(call) for call in message.get("tool_calls") or []
                    # ]

                res.raise_for_status()
        except requests.RequestException as e:
            raise ModelException(f"Model request failed: {e}") from e
        except json.JSONDecodeError as e:
            raise ModelException(f"Bad response from model: {e}") from e

        # TODO: Tools
        # if names and not reply.tool_calls and (calls := self.__text_calls(reply.content, names)):
        #     reply.content, reply.tool_calls = "", calls
        if on_text is not None and shown < len(reply.content):
            on_text(reply.content[shown:])
        return reply
