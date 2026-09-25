##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Guard Class: the rails of NeMo Guardrails, around the messages of the user and the replies of the model
##
## Usage:  guard = Guard()
##         verdict = guard.check_input(text)           before the message reaches the model
##         verdict = guard.check_output(text, reply)   before the reply reaches the user
##
import os
from .verdict import Verdict, PASS, MASKED, REFUSED
from logger.logger import log

# The rules: which rails run (config.yml), their flows (rails.co) and the code they call (actions.py)
CONFIG: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")

class Guard:
    """
        Guard Class: NeMo only checks the messages, it never talks to the user for Louis.
        The model is still called by OllamaModel: its tools, streaming and thinking stay as they are
    """
    def __init__(self, path: str = CONFIG):
        """ Load the rails of the given folder. NOTE: Raisable (NeMo missing, bad config) """
        # Imported here: with the guard off, Louis never loads NeMo (heavy, and not on Python 3.14)
        from nemoguardrails import LLMRails, RailsConfig

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
        if verdict.action != PASS:
            log.info(f"[guard] {stage} {verdict.action}{f' by {", ".join(stopped)}' if stopped else ''}")
        return verdict
