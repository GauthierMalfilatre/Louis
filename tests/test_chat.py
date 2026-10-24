##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the chatbot (B1): the reply of Ollama read as it streams, the history of the session sent each turn, the
## /commands, and the loop that reads the messages of the user. Ollama is faked: no model runs
##
import json
import pytest
import requests
import model.model as model_module
from command.command import Command, CommandTree
from events.event_bus import EventBus
from events.event_list import CHAT_TEXT, CHAT_TURN_ENDED, COMMAND_UNKNOWN, COMMAND_ERROR, SESSION_CREATED, APP_STOPPED
from model.model import OllamaModel
from model.model_exception import ModelException
from model.reply import Reply

class Streamed:
    """ What requests.post gives back for /api/chat: the lines Ollama streams """
    def __init__(self, chunks: list[dict]):
        self.lines: list[bytes] = [json.dumps(chunk).encode() for chunk in chunks]

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        return None

    def iter_lines(self):
        return iter(self.lines)

    def raise_for_status(self):
        return None

@pytest.fixture
def ollama(monkeypatch):
    """ A model whose /api/chat streams the chunks given: the payload it was sent is kept in sent """
    monkeypatch.setattr(OllamaModel, "_OllamaModel__probe", staticmethod(lambda uri, model: {"tools"}))
    sent: list[dict] = []

    def make(chunks: list[dict]) -> tuple[OllamaModel, list[dict]]:
        def post(url, json=None, **kwargs):
            sent.append(json)
            return Streamed(chunks)
        monkeypatch.setattr(model_module.requests, "post", post)
        return OllamaModel("http://ollama", "qwen3:8b"), sent
    return make

def done(**stats) -> dict:
    return {"done": True, "done_reason": "stop", "prompt_eval_count": 12, "eval_count": 3,
            "eval_duration": 1_500_000_000, **stats}

def test_the_reply_is_shown_piece_by_piece_as_ollama_streams_it(ollama):
    model, sent = ollama([{"message": {"content": "Bon"}}, {"message": {"content": "jour"}}, done()])
    pieces: list[str] = []
    reply: Reply = model.chat([{"role": "user", "content": "Salut"}], on_text=pieces.append)
    assert pieces == ["Bon", "jour"]
    assert reply.content == "Bonjour"
    assert (reply.prompt_tokens, reply.completion_tokens, reply.tokens) == (12, 3, 15)
    assert reply.generation == 1.5 and reply.ttft is not None and not reply.cut
    # The whole conversation goes with each request, and the context never changes size (Ollama would reload)
    assert sent[0]["messages"] == [{"role": "user", "content": "Salut"}]
    assert sent[0]["options"]["num_ctx"] > 0

def test_a_reply_cut_by_the_token_limit_says_so(ollama):
    model, _ = ollama([{"message": {"content": "Une longue"}}, done(done_reason="length")])
    assert model.chat([{"role": "user", "content": "?"}]).cut

def test_a_tool_call_written_as_text_is_read_as_a_call(ollama):
    tools = [{"type": "function", "function": {"name": "tree", "description": "", "parameters": {}}}]
    model, sent = ollama([{"message": {"content": '<tool_call>{"name": "tree", "arguments": {"depth": 1}}</tool_call>'}},
                          done()])
    pieces: list[str] = []
    reply: Reply = model.chat([{"role": "user", "content": "?"}], tools, on_text=pieces.append)
    assert [(call.name, call.arguments) for call in reply.tool_calls] == [("tree", {"depth": 1})]
    # Never shown to the user as text: it was a call
    assert reply.content == "" and pieces == []
    assert sent[0]["tools"] == tools

def test_an_error_of_ollama_or_of_the_network_is_a_model_exception(ollama, monkeypatch):
    model, _ = ollama([{"error": "model not found"}])
    with pytest.raises(ModelException, match="model not found"):
        model.chat([{"role": "user", "content": "?"}])

    def unreachable(*args, **kwargs):
        raise requests.ConnectionError("refused")
    monkeypatch.setattr(model_module.requests, "post", unreachable)
    with pytest.raises(ModelException, match="failed"):
        model.chat([{"role": "user", "content": "?"}])

def test_each_turn_sends_the_history_of_the_session(chat):
    app = chat([Reply(content="Bonjour Ada."), Reply(content="Tu t'appelles Ada.")])
    app._App__answer("Je m'appelle Ada")
    app._App__answer("Comment je m'appelle ?")
    second: list[dict] = app.sent[1]["messages"]
    assert second[0]["role"] == "system"
    assert [(message["role"], message["content"]) for message in second[1:]] == [
        ("user", "Je m'appelle Ada"), ("assistant", "Bonjour Ada."), ("user", "Comment je m'appelle ?")]
    # Streamed to the interface, and the turn ends well
    assert [data["text"] for data in app.listener.seen(CHAT_TEXT)] == ["Bonjour Ada.", "Tu t'appelles Ada."]
    assert [data["reason"] for data in app.listener.seen(CHAT_TURN_ENDED)] == ["done", "done"]

def test_a_model_that_fails_ends_the_turn_with_its_error(chat):
    app = chat([])
    def broken(*args, **kwargs):
        raise ModelException("Cannot reach http://ollama")
    app.model.chat = broken
    app._App__answer("Salut")
    [ended] = app.listener.seen(CHAT_TURN_ENDED)
    assert (ended["reason"], ended["message"]) == ("error", "Cannot reach http://ollama")

def test_the_loop_answers_the_messages_and_runs_the_commands_until_the_input_ends(chat):
    from conftest import Listener
    listener = Listener(typed=["Salut", "   ", "/clear", "Encore"])
    app = chat([Reply(content="Bonjour."), Reply(content="Re.")], listener=listener)
    first = app.session
    assert app.run() == 0
    # The blank message is skipped, /clear starts a new session: "Encore" is its first message
    assert len(app.sent) == 2
    assert app.session is not first
    assert [message["content"] for message in app.session.history if message["role"] == "user"] == ["Encore"]
    assert len(listener.seen(SESSION_CREATED)) == 2
    assert listener.seen(APP_STOPPED) == [{"reason": "eof"}]

class Echo(Command):
    def __init__(self):
        super().__init__("echo", alias=["e"], description="répète", usage="<texte>")
        self.got: list[str] = []

    def handle(self, app, arguments: str) -> None:
        self.got.append(arguments)

class Broken(Command):
    def __init__(self):
        super().__init__("broken")

    def handle(self, app, arguments: str) -> None:
        raise RuntimeError("boom")

class Bus:
    """ What the commands use of the app: its bus """
    def __init__(self):
        self.events = EventBus()
        self.seen: list = []
        self.events.subscribe(self.seen.append)

def test_a_command_gets_what_is_typed_after_its_name_or_alias():
    echo = Echo()
    tree, app = CommandTree().register(echo), Bus()
    assert tree.fetch("/echo  deux\nlignes", app) and tree.fetch("/e", app)
    assert echo.got == ["deux\nlignes", ""]

def test_a_path_is_a_message_and_an_unknown_command_is_told():
    tree, app = CommandTree().register(Echo()), Bus()
    assert not tree.fetch("/src/main.py, que fait ce fichier ?", app)
    assert not tree.fetch("bonjour", app)
    assert tree.fetch("/nope", app)
    [event] = app.seen
    assert event.name == COMMAND_UNKNOWN and event.data["name"] == "nope"
    assert event.data["commands"][0] == {"name": "echo", "usage": "<texte>", "description": "répète"}

def test_a_broken_command_is_told_and_never_stops_louis():
    tree, app = CommandTree().register(Broken()), Bus()
    assert tree.fetch("/broken", app)
    [event] = app.seen
    assert event.name == COMMAND_ERROR and event.data["reason"] == "failed" and "boom" in event.data["message"]

def test_two_commands_can_not_share_a_name():
    tree = CommandTree().register(Echo())
    with pytest.raises(ValueError):
        tree.register(Echo())
