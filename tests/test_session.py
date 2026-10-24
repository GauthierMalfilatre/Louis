##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the sessions and the profiles (M1): what is saved in SQLite and when, read back by another run, what the
## model is told of the user, and /sessions, /resume, /clear. The model is a script of replies: no Ollama
##
import sqlite3
from datetime import date
import pytest
from events.event_list import SESSION_LIST, SESSION_RESUMED, SESSION_SAVED, COMMAND_ERROR
from model.reply import Reply
from session.database import Database
from session.session import Session
from session.user import User
from tool.tool_call import ToolCall

@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "louis.db"))
    yield database
    database.close()

def test_a_session_is_only_saved_once_the_user_says_something(db):
    user = User.get_or_create(db, "ada")
    session = user.new_session("/projet")
    session.add("system", "Tu es Louis.")
    assert not session.saved
    session.add("user", "Salut")
    session.add("assistant", "", tool_calls=[ToolCall("tree", {"depth": 1})])
    session.add("tool", "/\n└── main.py", tool_name="tree")
    assert session.saved

    # Another run reads it back, the prompt and the tool calls with it
    again = Database(db.path)
    [saved] = User.get_or_create(again, "ada").sessions
    assert [message.role for message in saved.messages] == ["system", "user", "assistant", "tool"]
    assert saved.history[2]["tool_calls"] == [{"function": {"name": "tree", "arguments": {"depth": 1}}}]
    assert saved.history[3]["tool_name"] == "tree"
    assert saved.first_user_message() == "Salut" and saved.cwd == "/projet"
    again.close()

def test_a_conversation_where_the_user_said_nothing_is_never_kept(db):
    user = User.get_or_create(db, "ada")
    user.new_session("/projet").add("system", "Tu es Louis.")
    assert db.fetchone("SELECT COUNT(*) AS n FROM sessions")["n"] == 0

def test_a_user_is_found_again_by_its_name_with_its_own_sessions_only(db):
    ada, bob = User.get_or_create(db, "ada"), User.get_or_create(db, "bob")
    assert User.get_or_create(db, "ada").id == ada.id != bob.id
    for text in ("un", "deux"):
        ada.new_session("/p").add("user", text)
    bob.new_session("/p").add("user", "trois")
    sessions = User.get_or_create(db, "ada").sessions
    assert [session.first_user_message() for session in sessions] == ["un", "deux"]
    assert ada.get_session(sessions[0].id) is not None and ada.get_session(999) is None
    with pytest.raises(ValueError):
        User.get_or_create(db, "Anonymous")

def test_the_anonymous_user_never_writes_anything():
    user = User.anonymous()
    session = user.new_session("/p")
    session.add("user", "Salut")
    assert user.is_anonymous and not session.saved and session.messages[0].content == "Salut"

def test_an_older_database_gets_the_columns_added_since(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                "cwd TEXT NOT NULL, created_at TEXT NOT NULL)")
    old.close()
    db = Database(path)
    columns = {row["name"] for row in db.fetchall("PRAGMA table_info(sessions)")}
    assert {"title", "summary", "vector", "described_at"} <= columns
    db.close()

def test_the_model_is_told_who_the_user_is_and_the_date(chat, db):
    named = chat([], user=User.get_or_create(db, "ada"))
    prompt: str = named.session.messages[0].content
    assert "- Utilisateur : ada" in prompt and f"- Date : {date.today().isoformat()}" in prompt
    # Anonymous: no name to give
    assert "Utilisateur" not in chat([]).session.messages[0].content

def test_clear_starts_a_new_session_on_the_prompt_given(chat):
    app = chat([])
    first = app.session
    app._App__commands.fetch("/clear Tu es un tuteur de maths.", app)
    assert app.session is not first
    assert app.session.messages[0].content.startswith("Tu es un tuteur de maths.")

def test_sessions_lists_them_and_resume_brings_one_back_as_it_was(chat, db, folder):
    user = User.get_or_create(db, "ada")
    app = chat([Reply(content="Bonjour Ada."), Reply(content="Tu t'appelles Ada.")], user=user)
    app._App__answer("Je m'appelle Ada")
    first: Session = app.session
    assert app.listener.seen(SESSION_SAVED) == [{"id": first.id}]

    app._App__commands.fetch("/clear", app)
    app._App__commands.fetch("/sessions", app)
    [listing] = app.listener.seen(SESSION_LIST)
    assert [(s["id"], s["first_message"], s["here"]) for s in listing["sessions"]] == [(first.id, "Je m'appelle Ada", True)]

    app._App__commands.fetch(f"/resume {first.id}", app)
    [resumed] = app.listener.seen(SESSION_RESUMED)
    assert (resumed["last_question"], resumed["last_answer"]) == ("Je m'appelle Ada", "Bonjour Ada.")
    # The next message goes on from there: the model reads the whole conversation again
    app._App__answer("Comment je m'appelle ?")
    assert [m["content"] for m in app.sent[-1]["messages"] if m["role"] == "user"] == [
        "Je m'appelle Ada", "Comment je m'appelle ?"]

def test_resume_refuses_what_it_can_not_bring_back(chat, db, monkeypatch, tmp_path):
    anonymous = chat([])
    anonymous._App__commands.fetch("/resume 1", anonymous)
    assert anonymous.listener.seen(COMMAND_ERROR)[0]["reason"] == "anonymous"

    user = User.get_or_create(db, "ada")
    elsewhere = user.new_session("/ailleurs")
    elsewhere.add("user", "Salut")
    app = chat([], user=user)
    for typed in ("abc", "999", str(elsewhere.id)):
        app._App__commands.fetch(f"/resume {typed}", app)
    assert [error["reason"] for error in app.listener.seen(COMMAND_ERROR)] == ["usage", "not_found", "elsewhere"]
