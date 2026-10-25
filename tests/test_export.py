##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the export and the publication (X3): the document of a session, the files Louis wrote in it, its JSON,
## Markdown, HTML and PDF, then /share, /shares and /unshare and what the public link holds. No Ollama
##
import json
import pytest
from config.settings import settings
from events.event_list import EXPORT_DONE, SHARE_CREATED, SHARE_LIST, SHARE_REVOKED, COMMAND_ERROR
from export import render_json, render_md, render_html
from export.artifacts import collect, select
from export.document import build, conversation
from model.reply import Reply
from session.database import Database
from session.user import User
from share import store
from tool.tool_call import ToolCall

@pytest.fixture
def exports(tmp_path, monkeypatch):
    folder = tmp_path / "exports"
    monkeypatch.setitem(settings, "export.dir", str(folder))
    return folder

@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "louis.db"))
    yield database
    database.close()

def written(chat, user=None):
    """ A session where Louis wrote pendu.py, then answered """
    app = chat([Reply(content="J'écris le jeu.", tool_calls=[ToolCall("write_file", {"path": "pendu.py",
                                                                                     "content": "print('pendu')\n"})]),
                Reply(content="C'est fait : lance `python pendu.py`.")], user=user)
    app._App__answer("Écris un pendu en Python. Mon mail : ada@example.com")
    return app

def test_the_document_is_the_conversation_with_each_call_and_its_result(chat):
    app = written(chat)
    document = build(app.session, app.user)
    assert document["kind"] == "session" and document["title"].startswith("Écris un pendu en Python.")
    roles = [message["role"] for message in document["messages"]]
    # No system prompt, and the result of the call is in the reply that asked for it
    assert roles == ["user", "assistant", "assistant"]
    [call] = document["messages"][1]["tools"]
    assert (call["name"], call["ok"]) == ("write_file", True) and call["result"].startswith("OK")
    [file] = document["artifacts"]
    assert (file["path"], file["action"], file["source"], file["content"]) == (
        "/pendu.py", "created", "session", "print('pendu')\n")
    assert conversation(app.session) == document["messages"]

def test_the_files_are_rebuilt_from_their_edits_and_the_refused_ones_left_out(folder):
    messages = [{"role": "assistant", "content": "", "tools": [
        {"name": "write_file", "arguments": {"path": "a.py", "content": "x = 1\n"}, "result": "OK : /a.py créé", "ok": True},
        {"name": "edit_file", "arguments": {"path": "a.py", "old_str": "x = 1", "new_str": "x = 2"}, "result": "OK", "ok": True},
        {"name": "write_file", "arguments": {"path": "b.py", "content": "y\n"}, "result": "Refusé : non", "ok": False},
        {"name": "write_file", "arguments": {"path": "src/c.py", "content": "z\n"}, "result": "OK : /src/c.py créé", "ok": True},
    ]}]
    files = collect(messages, str(folder))
    assert [(file["path"], file["writes"], file["content"]) for file in files] == [
        ("/a.py", 2, "x = 2\n"), ("/src/c.py", 1, "z\n")]
    assert select(files, str(folder), ["src/"]) == ([files[1]], [])
    assert select(files, str(folder), ["*.py"])[0] == files
    assert select(files, str(folder), ["nope.py"]) == ([], ["nope.py"])

def test_each_format_renders_the_session(chat):
    app = written(chat)
    document = build(app.session, app.user)
    assert json.loads(render_json.render(document))["messages"] == document["messages"]
    markdown = render_md.render(document)
    assert "### Toi" in markdown and "### Louis" in markdown and "## Fichiers produits" in markdown
    assert "```python\nprint('pendu')\n```" in markdown
    page = render_html.render({**document, "messages": document["messages"] + [
        {"role": "user", "content": "<script>alert(1)</script>", "at": None}]})
    # What the user or the model wrote is never run by the page
    assert "<script>alert(1)" not in page and "&lt;script&gt;alert(1)" in page

def test_the_pdf_is_made_from_the_html():
    render_pdf = pytest.importorskip("export.render_pdf")
    try:
        output = render_pdf.render({"title": "t", "kind": "session", "session": {"id": 1}, "exported_at": None,
                                    "messages": [{"role": "user", "content": "Salut", "at": None}], "artifacts": []})
    except (ImportError, OSError) as e:
        pytest.skip(f"WeasyPrint or Pango missing: {e}")
    assert output.startswith(b"%PDF")

def test_export_writes_the_session_or_its_files_in_the_export_folder(chat, exports):
    app = written(chat)
    commands = app._App__commands
    commands.fetch("/export md", app)
    commands.fetch("/export --artifact pendu.py", app)
    whole, files = app.listener.seen(EXPORT_DONE)
    assert whole["format"] == "md" and whole["path"].startswith(str(exports)) and whole["path"].endswith(".md")
    assert "### Toi" in open(whole["path"], encoding="utf-8").read()
    assert files["format"] == "json" and files["files"] == ["/pendu.py"] and files["path"].endswith("-pendu.py.json")
    assert json.loads(open(files["path"], encoding="utf-8").read())["kind"] == "artifact"

def test_export_tells_what_it_can_not_do(chat, exports):
    app = chat([])
    for typed in ("/export doc", "/export", "/export 3"):
        app._App__commands.fetch(typed, app)
    assert [error["reason"] for error in app.listener.seen(COMMAND_ERROR)] == ["usage", "empty", "anonymous"]

def test_a_link_is_a_secret_token_that_can_be_closed(db):
    user = User.get_or_create(db, "ada")
    token = store.create(db, user.id, None, {"kind": "session", "title": "t", "messages": []})
    assert len(token) >= 22 and store.get(db, token)["title"] == "t"
    assert store.matching(db, user.id, token[:6]) == [token]
    assert store.matching(db, user.id, f"http://localhost:8080/s/{token}") == [token]
    assert store.matching(db, user.id, token[:3]) == []
    assert store.url(token).endswith(f"/s/{token}")
    assert store.revoke(db, user.id, token) and store.get(db, token) is None and not store.revoke(db, user.id, token)

def test_share_asks_each_time_masks_then_publishes(chat, db):
    app = written(chat, user=User.get_or_create(db, "ada"))
    app.listener.grant = False
    app._App__commands.fetch("/share", app)
    assert app.listener.seen(COMMAND_ERROR)[-1]["reason"] == "refused" and store.shares(db, app.user.id) == []

    app.listener.grant = True
    app._App__commands.fetch("/share", app)
    [shared] = app.listener.seen(SHARE_CREATED)
    assert shared["kind"] == "session" and shared["masked"] >= 1
    page = json.dumps(store.get(db, shared["token"]), ensure_ascii=False)
    # The public page never shows what the log would mask
    assert "ada@example.com" not in page and "<EMAIL_ADDRESS>" in page

    app._App__commands.fetch("/shares", app)
    assert [link["token"] for link in app.listener.seen(SHARE_LIST)[0]["shares"]] == [shared["token"]]
    app._App__commands.fetch(f"/unshare {shared['token'][:8]}", app)
    assert app.listener.seen(SHARE_REVOKED)[0]["token"] == shared["token"]
    assert store.get(db, shared["token"]) is None

def test_the_anonymous_user_can_not_share(chat):
    app = written(chat)
    for typed in ("/share", "/shares", "/unshare abcdef"):
        app._App__commands.fetch(typed, app)
    assert [error["reason"] for error in app.listener.seen(COMMAND_ERROR)] == ["anonymous"] * 3
