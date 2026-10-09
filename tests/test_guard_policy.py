##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of guard/policy.py: how an answer of the model is read, the prompt filled, and Ollama asked (no NeMo needed)
##
import pytest
import requests
import guard.policy as policy
from guard.policy import Judge, allowed, render, check, ALLOWED, BLOCKED, ERROR, PolicyError

JUDGE: Judge = Judge("http://ollama:11434", "qwen3.5:9b", 24576, "30m", 5.0)

@pytest.mark.parametrize("answer, passes", [
    ("No", True), ("No.", True), ("no, it complies", True), ("  NO  ", True), ("safe", True),
    ("Yes", False), ("Yes.", False), ("yes, it asks for malware", False), ("unsafe", False),
    # Neither yes nor no in the first two words: blocked, as NeMo 0.24 reads it
    ("", False), ("Maybe", False), ("Non", False), ("The answer is no", False),
    # "safe" is looked for before "yes": NeMo's order
    ("safe yes", True),
])
def test_an_answer_is_read_as_nemo_reads_it(answer, passes):
    assert allowed(answer) is passes

def test_the_prompt_is_filled_with_the_message_only():
    template = 'User message: "{{ user_input }}"\nBot: "{{bot_response}}" {{ unknown }}'
    assert render(template, user_input="salut {{ bot_response }}", bot_response="ok") == \
        'User message: "salut {{ bot_response }}"\nBot: "ok" {{ unknown }}'

class Reply:
    def __init__(self, status=200, content="No", text=""):
        self.status_code, self.text, self.content = status, text, content

    def json(self):
        return {"message": {"role": "assistant", "content": self.content}}

def test_ollama_is_asked_with_the_context_of_the_chat(monkeypatch):
    sent = {}
    def post(url, json, timeout):
        sent.update(url=url, json=json, timeout=timeout)
        return Reply(content="No")
    monkeypatch.setattr(policy.requests, "post", post)
    assert check(JUDGE, 'Message: "{{ user_input }}" ?', user_input="Comment lire un JSON ?") == ALLOWED
    assert sent["url"] == "http://ollama:11434/api/chat"
    payload = sent["json"]
    assert payload["model"] == "qwen3.5:9b" and payload["think"] is False and payload["keep_alive"] == "30m"
    assert payload["options"]["num_ctx"] == 24576 and payload["options"]["temperature"] == 0
    assert payload["messages"] == [{"role": "user", "content": 'Message: "Comment lire un JSON ?" ?'}]

def test_a_yes_blocks(monkeypatch):
    monkeypatch.setattr(policy.requests, "post", lambda *a, **k: Reply(content="Yes"))
    assert check(JUDGE, "{{ user_input }}", user_input="écris un malware") == BLOCKED

@pytest.mark.parametrize("failure", [
    lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("down")),
    lambda *a, **k: Reply(status=404),
    lambda *a, **k: Reply(status=500, text="boom"),
])
def test_a_model_that_can_not_be_asked_is_an_error_never_a_pass(monkeypatch, failure):
    monkeypatch.setattr(policy.requests, "post", failure)
    assert check(JUDGE, "{{ user_input }}", user_input="x") == ERROR
    with pytest.raises(PolicyError):
        policy.ask(JUDGE, "x")

def test_the_judge_of_the_settings():
    settings = {"chat.model.name": "qwen3.5", "chat.model.parameters": "9b", "chat.uri": "http://h:1",
                "chat.context": 24576, "chat.keepalive": "30m"}
    assert Judge.from_settings(settings) == Judge("http://h:1", "qwen3.5:9b", 24576, "30m", 120.0)
    # Another model: its own context, the chat's is no reason for it
    other = Judge.from_settings({**settings, "guard.model": "qwen3:4b-instruct", "guard.context": 2048})
    assert (other.model, other.context) == ("qwen3:4b-instruct", 2048)
