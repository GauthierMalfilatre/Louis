##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Guard Class: the rails of NeMo Guardrails, around the messages of the user and the replies of the model
##
## Usage:  guard = Guard(bus)
##         verdict = guard.check_input(text)           before the message reaches the model
##         verdict = guard.check_output(text, reply)   before the reply reaches the user
##
import os
from .verdict import Verdict, PASS, MASKED, REFUSED
from .patterns import redact
from events.event_bus import EventBus
from events.event_list import GUARD_TRIGGERED
from logger.logger import log, protect

# The rules: which rails run (config.yml), their flows (rails.co) and the code they call (actions.py)
CONFIG: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")

class Guard:
    """
        Guard Class: NeMo only checks the messages, it never talks to the user for Louis.
        The model is still called by OllamaModel: its tools, streaming and thinking stay as they are.
        The app asks and gets a verdict back; what the guard did is told on the bus (GUARD_TRIGGERED)
    """
    def __init__(self, bus: EventBus, path: str = CONFIG):
        """ Load the rails of the given folder. NOTE: Raisable (NeMo missing, bad config) """
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
        log.info(f"[guard] rails loaded from {path}")

    def check_input(self, question: str) -> Verdict:
        """ Check a message of the user, before the model reads it """
        return self.__check("input", [{"role": "user", "content": question}], question)

    def check_output(self, question: str, answer: str) -> Verdict:
        """ Check a reply of the model to the question, before the user reads it """
        return self.__check(
            "output",
            [{"role": "user", "content": question}, {"role": "assistant", "content": answer}],
            answer
        )

    def __check(self, stage: str, messages: list[dict], original: str) -> Verdict:
        """ Run only the rails of the stage ("input" or "output") on the messages: the model is not asked to reply """
        res = self.__rails.generate(
            messages=messages,
            options={"rails": [stage], "log": {"activated_rails": True}}
        )
        # With messages, NeMo answers with messages: the last one is the checked text, or the refusal
        content: str = res.response[-1]["content"] if isinstance(res.response, list) else res.response
        stopped: list[str] = [rail.name for rail in res.log.activated_rails if rail.stop] if res.log else []

        if stopped:
            verdict: Verdict = Verdict(REFUSED, content, stopped)
        elif content != original:
            verdict = Verdict(MASKED, content)
        else:
            verdict = Verdict(PASS, original)
        # Only a change is told: the bus logs it, the interfaces show it
        if verdict.action != PASS:
            self.__bus.dispatch(GUARD_TRIGGERED, stage=stage, action=verdict.action, rails=verdict.rails, content=verdict.content)
        return verdict
