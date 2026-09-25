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
from tool.tool_call import ToolCall
from logger.logger import log

CHAT_TIMEOUT: tuple[float, float] = (
    settings.get("chat.timeout.connect", 5.0),
    settings.get("chat.timeout.response", 600.0)
)

TOOL_CALL_OPEN : str = "<tool_call>"
TOOL_CALL_CLOSE: str = "</tool_call>"

class OllamaModel:
    """ Model Class, to chat with ollama API """
    def __init__(self, uri: str, model: str) -> "OllamaModel":
        """ Init the model class """
        self.__uri    = uri
        self.__model  = model
        self.__skills = OllamaModel.__probe(uri, model)
        self.__requests: int = 0
        log.info(f"[model] {model} at {uri}, capabilities: {', '.join(sorted(self.__skills))}")

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

    def chat(
            self,
            messages: list[dict],
            tools: list[dict] = [],
            images: list[str] = [],
            *,
            think: bool = False,
            on_text: Callable | None = None
        ) -> Reply:
        """ Send a conversation to the model, and returning its reply. Images are a list of path """
        payload: dict[str] = {
            "model": self.__model,
            "messages": messages,
            "stream": settings.get("chat.stream", True),
            # Without it, Ollama unloads the model after 5 minutes idle, and reloads it on the next message
            "keep_alive": settings.get("chat.keepalive", "30m"),
            # Must stay the same on every request: a different num_ctx makes Ollama reload the model
            "options": {"num_ctx": settings.get("chat.context", 12288)}
        }

        # The thinking is not shown: left on, it is a silent wait before every reply and tool call
        if self.thinking:
            payload["think"] = think

        if tools and self.tools:
            payload["tools"] = tools

        names: set[str] = {tool["function"]["name"] for tool in payload.get("tools") or []}

        reply: Reply = Reply()

        self.__requests += 1
        log.debug(f"[model] request #{self.__requests}: {len(messages)} messages, last one from {messages[-1]['role'] if messages else None}")
        thinking: str = ""
        stats: dict = {}

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
                    if chunk.get("done"):
                        stats = chunk
                    thinking += message.get("thinking") or ""
                    if text := message.get("content"):
                        reply.content += text
                        if on_text is not None and not (names and self.__maybe_call(reply.content)):
                            on_text(reply.content[shown:])
                            shown = len(reply.content)

                    reply.tool_calls += [
                        ToolCall.from_dict(call) for call in message.get("tool_calls") or []
                    ]

                res.raise_for_status()
        except requests.RequestException as e:
            raise ModelException(f"Model request failed: {e}") from e
        except json.JSONDecodeError as e:
            raise ModelException(f"Bad response from model: {e}") from e

        if names and not reply.tool_calls and (calls := self.__text_calls(reply.content, names)):
            log.debug(f"[model] tool calls written as text, parsed from:\n{reply.content}")
            reply.content, reply.tool_calls = "", calls
        if on_text is not None and shown < len(reply.content):
            on_text(reply.content[shown:])

        reply.tokens = stats.get("prompt_eval_count", 0) + stats.get("eval_count", 0)
        OllamaModel.__log_reply(reply, thinking, stats)
        return reply

    @staticmethod
    def __log_reply(reply: Reply, thinking: str, stats: dict) -> None:
        """ Log what the model thought and answered, and how long Ollama took """
        if thinking:
            log.debug(f"[model] thinking:\n{thinking}")
        if reply.content:
            log.info(f"[model] reply:\n{reply.content}")
        for call in reply.tool_calls:
            log.info(f"[model] tool call {call.name} {json.dumps(call.arguments, ensure_ascii=False)}")

        def seconds(key: str) -> float:
            return stats.get(key, 0) / 1e9
        generated: int = stats.get("eval_count", 0)
        speed: float = generated / seconds("eval_duration") if stats.get("eval_duration") else 0.0
        log.debug(
            f"[model] prompt {stats.get('prompt_eval_count', 0)} tokens in {seconds('prompt_eval_duration'):.2f}s, "
            f"generated {generated} tokens in {seconds('eval_duration'):.2f}s ({speed:.1f} tok/s), "
            f"load {seconds('load_duration'):.2f}s, total {seconds('total_duration'):.2f}s, "
            f"done: {stats.get('done_reason')}"
        )

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
