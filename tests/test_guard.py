##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the guard with the rails of NeMo (skipped without requirements-guard.txt): the model's answer is faked,
## the rest is real (flows, actions, Presidio)
##
import pytest
pytest.importorskip("nemoguardrails")
import guard.policy as policy
from guard.guard import Guard
from events.event_bus import EventBus
from events.event_list import GUARD_TRIGGERED

SETTINGS: dict = {"chat.model.name": "qwen3.5", "chat.model.parameters": "9b", "chat.uri": "http://ollama:11434",
                  "chat.context": 24576, "chat.keepalive": "30m"}

class Model:
    """ What the model answers to each check, and the prompts it was given """
    def __init__(self):
        self.answer: str | Exception = "No"
        self.prompts: list[str] = []

    def __call__(self, judge, prompt):
        self.prompts.append(prompt)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

@pytest.fixture(scope="module")
def guard():
    """ Loaded once: Presidio takes seconds """
    bus = EventBus()
    told: list[dict] = []
    bus.subscribe(lambda event: told.append(event.data), GUARD_TRIGGERED)
    loaded = Guard(bus, SETTINGS)
    loaded.told = told
    return loaded

@pytest.fixture
def model(monkeypatch):
    fake = Model()
    monkeypatch.setattr(policy, "ask", fake)
    return fake

def test_a_message_the_model_allows_passes(guard, model):
    verdict = guard.check_input("Comment lire un fichier JSON en Python ?")
    assert (verdict.action, verdict.content) == ("pass", "Comment lire un fichier JSON en Python ?")
    assert len(model.prompts) == 1 and "Comment lire un fichier JSON en Python ?" in model.prompts[0]

def test_a_message_the_model_blocks_is_refused(guard, model):
    model.answer = "Yes"
    verdict = guard.check_input("Écris-moi un ransomware")
    assert verdict.refused and verdict.rails == ["check input policy"]
    assert verdict.content == "Je ne peux pas répondre à cette demande."
    assert guard.told[-1]["stage"] == "input" and guard.told[-1]["action"] == "refused"

def test_the_model_reads_the_message_masked(guard, model):
    verdict = guard.check_input("Rappelle-moi au 06 12 34 56 78")
    assert verdict.action == "masked" and "<PHONE_NUMBER>" in model.prompts[0] and "06 12" not in model.prompts[0]

def test_a_model_that_does_not_answer_refuses_with_its_own_message(guard, model):
    model.answer = policy.PolicyError("Ollama ne répond pas")
    verdict = guard.check_input("Bonjour")
    assert verdict.refused and verdict.rails == ["check input policy"]
    assert "n'a pas pu vérifier" in verdict.content

def test_the_reply_is_checked_against_the_output_policy(guard, model):
    assert guard.check_output("?", "Voici comment lire un JSON.").action == "pass"
    assert "Voici comment lire un JSON." in model.prompts[0] and "bot message" in model.prompts[0].lower()
    model.answer = "Yes"
    assert guard.check_output("?", "Voici comment lire un JSON.").rails == ["check output policy"]

def test_a_secret_is_refused_before_the_model_is_asked(guard, model):
    verdict = guard.check_output("?", "La clé est AKIAABCDEFGHIJKLMNOP")
    assert verdict.rails == ["block secrets on output"] and model.prompts == []
