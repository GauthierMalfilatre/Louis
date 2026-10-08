##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Guard Class: the rails of NeMo Guardrails, around the messages of the user and the replies of the model
##
## Usage:  guard = Guard(bus)
##         verdict = guard.check_input(text)           before the message reaches the model
##         verdict = guard.check_output(text, reply)   before the reply reaches the user
##         verdict = guard.check_tool_call(call)       before the tool the model asked for runs
##         verdict = guard.check_tool_result(tool, result)   before the model reads what a tool gave (see screens_result)
##
import os
import requests
from .verdict import Verdict, PASS, MASKED, REFUSED
from .patterns import redact
from tool.tool_call import ToolCall
from events.event_bus import EventBus
from events.event_list import GUARD_TRIGGERED, GUARD_RELOADS
from logger.logger import log, protect

# The rules: which rails run (config.yml), their flows (rails.co) and the code they call (actions.py)
CONFIG: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")

class Guard:
    """
        Guard Class: NeMo only checks the messages, it never talks to the user for Louis.
        The model is still called by OllamaModel: its tools, streaming and thinking stay as they are.
        The app asks and gets a verdict back; what the guard did is told on the bus (GUARD_TRIGGERED)
    """
    def __init__(self, bus: EventBus, path: str = CONFIG, context: int | None = None):
        """
            Load the rails of the given folder. context is the num_ctx of the chat: after the first check, the guard
            tells (GUARD_RELOADS) if Ollama loaded the model with another one for NeMo. NOTE: Raisable (NeMo missing,
            bad config)
        """
        # The log sees everything before the rails do (the message typed, the reply, what a tool read):
        # it keeps it only masked
        protect(redact)
        # Imported here: with the guard off, Louis never loads NeMo (heavy, and not on Python 3.14)
        try:
            from nemoguardrails import LLMRails, RailsConfig
        except ImportError as e:
            raise ImportError(f"guard.enabled needs NeMo Guardrails: pip install -r requirements-guard.txt ({e})") from e

        self.__bus  : EventBus = bus
        self.__rails = LLMRails(RailsConfig.from_path(path))
        self.__context: int | None = context
        # Checked once, after the first request NeMo made
        self.__probed : bool       = context is None
        log.info(f"[guard] rails loaded from {path}")

    def check_input(self, question: str) -> Verdict:
        """ Check a message of the user, before the model reads it """
        return self.__check("input", "input", [{"role": "user", "content": question}], question)

    def check_output(self, question: str, answer: str) -> Verdict:
        """ Check a reply of the model to the question, before the user reads it """
        return self.__check(
            "output", "output",
            [{"role": "user", "content": question}, {"role": "assistant", "content": answer}],
            answer
        )

    def check_tool_call(self, call: ToolCall) -> Verdict:
        """ Check a call the model asks for, before the tool runs: it passes or is refused, never masked """
        request: dict = {"id": call.name, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}
        return self.__check(
            "tool_call", "tool_output",
            [{"role": "assistant", "content": "", "tool_calls": [request]}],
            None, tool=call.name
        )

    def screens_result(self, tool: str) -> bool:
        """ Check if the results of a tool go through the rails before the model reads them (untrusted_tools) """
        return tool in (((self.__rails.config.custom_data or {}).get("guard") or {}).get("untrusted_tools") or [])

    def check_tool_result(self, tool: str, result: str) -> Verdict:
        """ Check what a tool gave, before the model reads it: it passes, is masked, or is replaced by a refusal """
        # A tool message is checked with the request it answers: the name of the tool stands for it
        return self.__check(
            "tool_result", "tool_input",
            [{"role": "user", "content": tool}, {"role": "tool", "content": result, "name": tool, "tool_call_id": tool}],
            result, variable="tool_message", tool=tool
        )

    def __probe(self) -> None:
        """
            The context Ollama loaded the model of NeMo with (/api/ps), against the chat's: when they differ, every check
            reloads the model, and the next request of the chat reloads it again (12 to 18 s each with qwen3.5:9b on
            a laptop). Nothing NeMo sends can change it: told once, with what to set where Ollama starts
        """
        main = next((model for model in self.__rails.config.models if model.type == "main"), None)
        if main is None or main.engine != "ollama":
            return
        uri: str = str((main.parameters or {}).get("base_url") or "http://localhost:11434").removesuffix("/").removesuffix("/v1")
        try:
            loaded: dict = {model["name"]: model.get("context_length")
                            for model in requests.get(f"{uri}/api/ps", timeout=2.0).json().get("models", [])}
        except (requests.RequestException, ValueError):
            return
        context: int | None = loaded.get(main.model)
        if context is None or context == self.__context:
            return
        message: str = (
            f"Le garde-fou fait recharger {main.model} à chaque vérification : Ollama le charge avec {context} tokens de "
            f"contexte pour NeMo, et Louis avec {self.__context} (chat.context), chaque changement prend plusieurs "
            f"secondes. Relance Ollama avec OLLAMA_CONTEXT_LENGTH={self.__context} OLLAMA_KEEP_ALIVE=30m (variables "
            "de son service, ou devant ollama serve)."
        )
        log.warning(f"[guard] {main.model} loaded with num_ctx {context} for NeMo, {self.__context} for the chat: "
                    "it is reloaded on every check")
        self.__bus.dispatch(GUARD_RELOADS, model=main.model, loaded=context, expected=self.__context, message=message)

    def hide(self, arguments: dict) -> dict:
        """
            The arguments of a call as the user sees them: masked the way the log is. Only what is shown:
            the tool runs on the real ones
        """
        return {key: redact(value) if isinstance(value, str) else value for key, value in arguments.items()}

    def __check(self, stage: str, rails: str, messages: list[dict], original: str | None,
                variable: str | None = None, **told) -> Verdict:
        """
            Run only the rails of NeMo (input, output, tool_output, tool_input) on the messages: the model is not asked
            to reply. Without an original text, what NeMo answers is only a refusal, or nothing to take.
            The tool_input rails answer nothing but a refusal: the checked text, masked, is the variable they rewrite
        """
        options: dict = {"rails": [rails], "log": {"activated_rails": True}}
        if variable:
            options["output_vars"] = [variable]
        res = self.__rails.generate(messages=messages, options=options)
        if not self.__probed:
            self.__probed = True
            self.__probe()
        # With messages, NeMo answers with messages: the last one is the checked text, or the refusal
        content: str = res.response[-1]["content"] if isinstance(res.response, list) else res.response
        stopped: list[str] = [rail.name for rail in res.log.activated_rails if rail.stop] if res.log else []
        if variable and not stopped:
            content = (res.output_data or {}).get(variable, original)

        if stopped:
            verdict: Verdict = Verdict(REFUSED, content, stopped)
        elif original is not None and content != original:
            verdict = Verdict(MASKED, content)
        else:
            verdict = Verdict(PASS, original or "")
        # Only a change is told: the bus logs it, the interfaces show it
        if verdict.action != PASS:
            self.__bus.dispatch(
                GUARD_TRIGGERED, stage=stage, action=verdict.action, rails=verdict.rails, content=verdict.content, **told
            )
        return verdict
