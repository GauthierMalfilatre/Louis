##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the scribe (titles, summaries, welcome), of /find, and of the summary of what leaves the context
##
import json
import sqlite3
import threading
import numpy as np
import pytest
import session.scribe as scribe_module
from app.context_window import ContextWindow
from config.prompt import NUDGE_PROMPT, SUMMARY_ASKED, SUMMARY_TITLE
from events.event_bus import EventBus
from events.event_list import SESSION_CREATED, SESSION_SAVED, CHAT_TURN_ENDED, SESSION_DESCRIBED, APP_WELCOME
from session.database import Database
from session.message import Message
from session.scribe import Scribe, transcript, one_line, packed
from session.search import find
from session.user import User
from tool.tool_call import ToolCall

def test_a_transcript_tells_what_was_done_not_what_was_cancelled():
    text: str = transcript([
        Message("system", "Tu es Louis."),
        Message("user", "Ajoute sub à calc.py"),
        Message("assistant", "", [ToolCall("edit_file", {"path": "calc.py"})]),
        Message("tool", "OK", tool_name="edit_file"),
        Message("assistant", "C'est fait."),
        Message("user", NUDGE_PROMPT),
        Message("user", "Écris un poème sur la mer"),
    ])
    assert text == ("Utilisateur : Ajoute sub à calc.py\n[Louis a utilisé edit_file sur calc.py]\nLouis : C'est fait.\n"
                    "Utilisateur : Écris un poème sur la mer\n(interrompu, sans réponse)")

def test_a_long_transcript_keeps_its_start_and_its_end():
    text: str = transcript([Message("user", f"demande {i} " + "x" * 280) if i % 2 == 0 else Message("assistant", "ok")
                            for i in range(60)])
    assert text.startswith("Utilisateur : demande 0") and "[…]" in text and "demande 58" in text
    assert len(text) <= scribe_module.TRANSCRIPT_CHARS + 10

def test_what_the_model_writes_is_kept_on_one_line():
    assert one_line(' « **Ajout de sub**\n dans calc.py » ', 60) == "Ajout de sub dans calc.py"
    assert one_line("a" * 100, 10) == "aaaaaaaaa…"

class Ollama:
    """ What the scribe asks of Ollama, answered as Ollama would, with what it was asked kept """
    def __init__(self, answers: dict[str, dict]):
        self.answers: dict[str, dict] = answers
        self.asked: list[dict] = []

    def post(self, url: str, **request) -> "Ollama.Response":
        body: dict = request["json"]
        self.asked.append(body)
        key: str = "describe" if "carnet" in body["messages"][0]["content"] else "welcome"
        return Ollama.Response({"message": {"content": json.dumps(self.answers[key])}})

    class Response:
        status_code = 200

        def __init__(self, data: dict):
            self.data: dict = data

        def json(self) -> dict:
            return self.data

SETTINGS: dict = {"chat.uri": "http://ollama", "scribe.model": "qwen3:4b-instruct", "rag.embed.model": ""}

@pytest.fixture
def saved(tmp_path, monkeypatch):
    """ A user with a session where something was done, in a database, in the folder Louis runs in """
    monkeypatch.chdir(tmp_path)
    path: str = str(tmp_path / "louis.db")
    db: Database = Database(path)
    user: User = User.get_or_create(db, "ada")
    session = user.new_session(str(tmp_path))
    session.add("user", "Ajoute sub à calc.py")
    session.add("assistant", "C'est fait.")
    yield path, user, session
    db.close()

def wait_for(bus: EventBus, name: str) -> tuple[dict, threading.Event]:
    """ The data of the next event of this name, dispatched from the thread of the scribe """
    told: dict = {}
    done: threading.Event = threading.Event()
    bus.subscribe(lambda event: (told.update(event.data), done.set()), name)
    return told, done

def test_a_session_is_described_once_a_reply_is_done(saved, monkeypatch):
    path, user, session = saved
    ollama: Ollama = Ollama({"describe": {"title": "Ajout de sub.", "summary": "Tu as ajouté sub à calc.py."},
                             "welcome": {"lead": "On teste sub ?"}})
    monkeypatch.setattr(scribe_module.requests, "post", ollama.post)
    bus: EventBus = EventBus()
    told, done = wait_for(bus, SESSION_DESCRIBED)
    Scribe(SETTINGS, bus, path, user.id, welcome=False)
    bus.dispatch(SESSION_SAVED, id=session.id)
    bus.dispatch(CHAT_TURN_ENDED, reason="done", message=None)
    assert done.wait(5)
    assert told == {"id": session.id, "title": "Ajout de sub", "summary": "Tu as ajouté sub à calc.py."}
    # On the CPU, the chat model keeps the GPU
    assert ollama.asked[0]["options"]["num_gpu"] == 0 and ollama.asked[0]["think"] is False
    row = sqlite3.connect(path).execute("SELECT title, summary FROM sessions WHERE id = ?", (session.id,)).fetchone()
    assert row == ("Ajout de sub", "Tu as ajouté sub à calc.py.")

def test_a_new_session_is_welcomed_from_the_last_one(saved, monkeypatch):
    path, user, session = saved
    sqlite3.connect(path, isolation_level=None).execute(
        "UPDATE sessions SET title = 'Ajout de sub', summary = 'Tu as ajouté sub.' WHERE id = ?", (session.id,))
    ollama: Ollama = Ollama({"welcome": {"lead": "« On teste sub dans calc.py ? »"}})
    monkeypatch.setattr(scribe_module.requests, "post", ollama.post)
    bus: EventBus = EventBus()
    told, done = wait_for(bus, APP_WELCOME)
    Scribe(SETTINGS, bus, path, user.id)
    bus.dispatch(SESSION_CREATED, user="ada", persistent=True, custom_prompt=False)
    assert done.wait(5)
    assert told == {"lead": "On teste sub dans calc.py ?"}
    assert "Dernière session : « Ajout de sub » — Tu as ajouté sub." in ollama.asked[0]["messages"][1]["content"]

class Embedder:
    """ Vectors on two axes: JSON, and the sea """
    def query(self, text: str) -> list[float]:
        return [1.0, 0.0] if "json" in text.lower() else [0.0, 1.0]

def test_a_session_is_found_by_its_meaning_or_by_its_words(saved):
    path, user, session = saved
    other = user.new_session(session.cwd)
    other.add("user", "Écris un poème")
    db: Database = Database(path)
    db.execute("UPDATE sessions SET title = ?, vector = ? WHERE id = ?", ("Lire un fichier JSON", packed([0.9, 0.1]), session.id))
    db.execute("UPDATE sessions SET title = ?, vector = ? WHERE id = ?", ("Poème sur la mer", packed([0.1, 0.9]), other.id))
    sessions, mode = find(db, user.id, "parser du json", Embedder(), session.cwd)
    assert mode == "meaning" and [found["id"] for found in sessions] == [session.id]
    # Without the embedding model, by the words of the question, accents or not
    sessions, mode = find(db, user.id, "poeme", None, session.cwd)
    assert mode == "words" and [found["id"] for found in sessions] == [other.id]
    db.close()

def test_an_old_database_gets_the_columns_of_the_scribe(tmp_path):
    path: str = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.executescript("CREATE TABLE sessions (id INTEGER PRIMARY KEY, user_id INTEGER, cwd TEXT, created_at TEXT);")
    old.close()
    db: Database = Database(path)
    assert {"title", "summary", "vector", "described_at"} <= {row["name"] for row in db.fetchall("PRAGMA table_info(sessions)")}
    db.close()

def test_what_leaves_the_context_is_summed_up_once():
    asked: list[tuple[str, list[dict]]] = []

    def summarize(previous: str, left: list[dict]) -> str:
        asked.append((previous, left))
        return f"résumé {len(asked)}"

    window: ContextWindow = ContextWindow(1000, [], summarize)
    history: list[dict] = [{"role": "system", "content": "prompt"}]
    for i in range(12):
        history += [{"role": "user", "content": f"demande {i} " + "x" * 400},
                    {"role": "assistant", "content": f"réponse {i} " + "y" * 400}]
    # An estimate never asks the model
    messages, cut = window.view(history, summarize=False)
    assert cut["dropped"] and not cut["summarized"] and not asked
    # The next request sums up what was left out, and reads it right after its system prompt, as what it said itself
    messages, cut = window.view(history)
    assert cut == {"results": 0, "dropped": 0, "summarized": True}
    assert len(asked) == 1 and asked[0][0] == "" and asked[0][1][0]["content"].startswith("demande 0")
    assert messages[:3] == [{"role": "system", "content": "prompt"}, {"role": "user", "content": SUMMARY_ASKED},
                            {"role": "assistant", "content": SUMMARY_TITLE + "résumé 1"}]
    # Nothing more left out: not asked again, the summary stays
    messages, cut = window.view(history)
    assert cut is None and len(asked) == 1 and messages[2]["content"].endswith("résumé 1")
    window.reset()
    assert len(window.view(history[:3])[0]) == 3

def test_a_failed_summary_only_leaves_out():
    window: ContextWindow = ContextWindow(1000, [], lambda previous, left: None)
    history: list[dict] = [{"role": "system", "content": "prompt"}] + [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "z" * 500} for i in range(20)
    ]
    messages, cut = window.view(history)
    assert cut["dropped"] and cut["summarized"] is False and messages[1]["content"] != SUMMARY_ASKED

def test_a_packed_vector_is_of_length_one():
    assert np.isclose(np.linalg.norm(np.frombuffer(packed([3.0, 4.0]), dtype=np.float32)), 1.0)

def test_the_sessions_of_before_are_described_when_nothing_else_is_asked(saved, monkeypatch):
    path, user, session = saved
    monkeypatch.setattr(scribe_module, "IDLE", 0.05)
    monkeypatch.setattr(scribe_module.requests, "post", Ollama({"describe": {"title": "Ajout de sub", "summary": "Tu as ajouté sub."}}).post)
    bus: EventBus = EventBus()
    told, done = wait_for(bus, SESSION_DESCRIBED)
    Scribe(SETTINGS, bus, path, user.id, welcome=False)
    assert done.wait(5) and told["id"] == session.id
