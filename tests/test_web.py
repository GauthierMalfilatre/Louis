##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the web interface: what the pages see of a turn, what they send, the permissions, Stop, the shared pages
##
import http.client
import json
import os
import sqlite3
import subprocess
import threading
import time
import pytest
from events.event import Event
from events.event_bus import EventBus
from events.event_list import APP_STARTED, SESSION_CREATED, SESSION_RESUMED, CHAT_TURN_STARTED, CHAT_TURN_ENDED
from events.event_list import CHAT_TEXT, CHAT_REPLY, TOOL_CALL_STARTED, TOOL_CALL_ENDED, RAG_INDEXED
from events.event_list import MODEL_CALL, RAG_RETRIEVED, CHAT_NUDGED
from interface.web import WebInterface, history_items, stats, project, tool_object
from logger.logger import log_event
from session.database import Database
from session.user import User
from share import store
from tool.permission import PermissionManager

def request(web: WebInterface, method: str, path: str, body: dict | None = None,
            headers: dict | None = None) -> tuple[int, dict, str]:
    """ One request to the server, as a page sends it: its status, its headers and its body """
    port: int = int(web.url.rsplit(":", 1)[1])
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    sent: dict = {"Content-Type": "application/json"} if body is not None else {}
    connection.request(method, path, json.dumps(body) if body is not None else None, {**sent, **(headers or {})})
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read().decode()
    connection.close()
    return result

def snapshot(web: WebInterface) -> dict:
    """ What a page that connects now is given """
    return json.loads(web.subscribe().get_nowait())

def started(bus: EventBus, persistent: bool = False) -> None:
    """ What the app tells before the first message """
    bus.dispatch(APP_STARTED, model="qwen3:8b", think=False, commands=[{"name": "clear", "usage": "", "description": ""}])
    bus.dispatch(SESSION_CREATED, user="ada" if persistent else "Anonymous", persistent=persistent, custom_prompt=False)

@pytest.fixture
def served(tmp_path):
    """ The web interface on a free port, bound to a bus, without a database unless a test gives one """
    web: WebInterface = WebInterface("127.0.0.1", 0, str(tmp_path / "louis.db"))
    bus: EventBus = EventBus()
    web.bind(bus)
    with web:
        yield web, bus

def test_a_turn_reaches_the_pages(served):
    web, bus = served
    started(bus)
    assert request(web, "POST", "/api/messages", {"text": "Lis main.py"})[0] == 202
    assert web.getUserInput() == "Lis main.py"

    bus.dispatch(CHAT_TURN_STARTED)
    bus.dispatch(TOOL_CALL_STARTED, name="cat_file", arguments={"path": "main.py"}, producer="model")
    bus.dispatch(TOOL_CALL_ENDED, name="cat_file", producer="model", ok=True,
                 result="/main.py (lignes 1-2 sur 2)\n1 | a\n2 | b", duration=0.2)
    bus.dispatch(CHAT_TEXT, text="Il **lit**")
    bus.dispatch(CHAT_TEXT, text=" deux lignes.")
    bus.dispatch(CHAT_REPLY, content="Il **lit** deux lignes.", tools=[])
    bus.dispatch(CHAT_TURN_ENDED, reason="done", message=None)

    shown: dict = snapshot(web)
    assert shown["state"]["model"] == "qwen3:8b" and shown["state"]["busy"] is True
    user, call, text = shown["log"]
    assert user == {"kind": "user", "text": "Lis main.py", "id": user["id"]}
    assert (call["label"], call["detail"], call["status"], call["summary"]) == ("Lecture", "main.py", "ok", "2 lignes lues")
    assert text["done"] and text["html"] == "<p>Il <strong>lit</strong> deux lignes.</p>\n"

def test_the_events_stream_starts_with_what_is_shown(served):
    web, bus = served
    started(bus)
    port: int = int(web.url.rsplit(":", 1)[1])
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", "/api/events")
    response = connection.getresponse()
    assert response.getheader("Content-Type").startswith("text/event-stream")
    line: bytes = response.fp.readline()
    assert line.startswith(b"data: ") and json.loads(line[6:])["type"] == "snapshot"
    connection.close()

def test_a_message_is_refused_while_louis_works(served):
    web, bus = served
    started(bus)
    assert request(web, "POST", "/api/messages", {"text": "un"})[0] == 202
    status, _, body = request(web, "POST", "/api/messages", {"text": "deux"})
    assert status == 409 and "travaille" in json.loads(body)["error"]

def test_a_button_command_is_not_shown_as_a_message(served):
    web, bus = served
    started(bus)
    request(web, "POST", "/api/messages", {"text": "/think", "shown": False})
    assert web.getUserInput() == "/think"
    assert snapshot(web)["log"] == []

def test_only_a_reply_shows_louis_answering(served):
    web, bus = served
    started(bus)
    # A command (/think): busy while it runs, never a turn, free again as soon as the app asks for the next message
    request(web, "POST", "/api/messages", {"text": "/think", "shown": False})
    web.getUserInput()
    assert snapshot(web)["state"]["turn"] is False
    def wait() -> None:
        """ The app waiting for the next message, until the server closes """
        with pytest.raises(EOFError):
            web.getUserInput()

    threading.Thread(target=wait, daemon=True).start()
    for _ in range(100):
        if not snapshot(web)["state"]["busy"]:
            break
        time.sleep(0.01)
    assert snapshot(web)["state"]["busy"] is False
    # A message: the model answers from the start of its turn to its end
    bus.dispatch(CHAT_TURN_STARTED)
    assert snapshot(web)["state"]["turn"] is True
    bus.dispatch(CHAT_TURN_ENDED, reason="cancelled", message=None)
    assert snapshot(web)["state"]["turn"] is False

def reply(written: int, generation: float, ttft: float | None = 0.5, load: float = 0.0) -> dict:
    """ A Reply of the model as MODEL_CALL gives it """
    return {"content": "", "tool_calls": [], "cut": False, "prompt_tokens": 1000, "completion_tokens": written,
            "ttft": ttft, "load": load, "prompt_eval": 0.1, "generation": generation, "done": "stop"}

def test_stats_sum_up_the_requests_of_a_turn():
    assert stats([]) is None
    summed: dict = stats([{**reply(100, 2.0, load=7.5), "latency": 10.0}, {**reply(60, 2.0, ttft=0.2), "latency": 2.5}])
    assert summed == {"calls": 2, "tokens": 160, "prompt": 2000, "speed": 40.0, "ttft": 0.5, "load": 7.5, "latency": 12.5}
    assert stats([{**reply(0, 0.0, ttft=None), "latency": 0.3}])["speed"] is None

def test_a_turn_ends_with_its_references_and_its_cost(served):
    web, bus = served
    started(bus)
    bus.dispatch(CHAT_TURN_STARTED)
    assert snapshot(web)["state"]["started"] is not None
    bus.dispatch(TOOL_CALL_STARTED, name="search_knowledge", arguments={"query": "json"}, producer="model")
    bus.dispatch(RAG_RETRIEVED, query="json", mode="hybrid", reranker=None, hits=[
        {"source": "docs", "path": "/json.md", "start": 1, "end": 11, "score": 0.0328, "fused": None}
    ])
    bus.dispatch(TOOL_CALL_ENDED, name="search_knowledge", producer="model", ok=True, result="[1] docs /json.md", duration=0.1)
    bus.dispatch(MODEL_CALL, status="ok", latency=3.0, reply=reply(120, 3.0))
    bus.dispatch(MODEL_CALL, status="error", error="Cannot reach", latency=0.1, reply=None)
    bus.dispatch(CHAT_REPLY, content="Je vais le faire.", tools=[])
    bus.dispatch(CHAT_NUDGED)
    bus.dispatch(CHAT_TURN_ENDED, reason="done", message=None)

    shown: dict = snapshot(web)
    tool, text, note, cost = shown["log"]
    assert tool["sources"]["hits"] == [{"source": "docs", "path": "/json.md", "start": 1, "end": 11, "score": 0.03}]
    assert (text["kind"], note["kind"]) == ("text", "note")
    assert (cost["kind"], cost["calls"], cost["tokens"], cost["speed"]) == ("stats", 1, 120, 40.0)
    assert shown["state"]["started"] is None and shown["state"]["turn"] is False

def test_the_sidebar_asks_the_sessions_first(served):
    web, bus = served
    started(bus, persistent=True)
    assert web.getUserInput() == "/sessions"

def test_other_sites_are_refused(served):
    web, bus = served
    assert request(web, "GET", "/", headers={"Host": "evil.example"})[0] == 403
    assert request(web, "POST", "/api/messages", {"text": "hi"}, {"Origin": "http://evil.example"})[0] == 403
    port: int = int(web.url.rsplit(":", 1)[1])
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("POST", "/api/messages", "text=hi", {"Content-Type": "application/x-www-form-urlencoded"})
    assert connection.getresponse().status == 415

def test_the_page_is_served_with_its_policy(served):
    web, _ = served
    status, headers, body = request(web, "GET", "/")
    assert status == 200 and "<title>Louis</title>" in body
    assert "connect-src 'self'" in headers["Content-Security-Policy"]

def test_a_permission_is_answered_by_a_page(served):
    web, bus = served
    started(bus)
    permissions: PermissionManager = PermissionManager(bus)

    def answer(choice: str) -> None:
        """ The page answers once the question is shown """
        for _ in range(200):
            asked: list[dict] = [item for item in snapshot(web)["log"] if item.get("status") == "pending"]
            if asked:
                request(web, "POST", "/api/permission", {"id": asked[0]["request"], "choice": choice})
                return
            time.sleep(0.01)

    page = threading.Thread(target=answer, args=("a",))
    page.start()
    assert permissions.request("write_file", "Création de /a.py", "+print(1)") is True
    page.join()
    # "Always" for this tool: not asked again in this session, but a share is asked every time
    assert permissions.request("write_file", "Création de /b.py") is True
    page = threading.Thread(target=answer, args=("n",))
    page.start()
    assert permissions.request("share", "Publier ?", every_time=True) is False
    page.join()
    statuses: list[str] = [item["status"] for item in snapshot(web)["log"] if item["kind"] == "permission"]
    assert statuses == ["always", "auto", "refused"]
    assert request(web, "POST", "/api/permission", {"id": 1, "choice": "y"})[0] == 409

def test_stop_cancels_what_louis_does_never_louis_itself(served):
    web, bus = served
    started(bus)
    assert request(web, "POST", "/api/stop", {})[0] == 409
    request(web, "POST", "/api/messages", {"text": "un long poème"})
    web.getUserInput()
    bus.dispatch(CHAT_TURN_STARTED)
    threading.Timer(0.1, lambda: request(web, "POST", "/api/stop", {})).start()
    with pytest.raises(KeyboardInterrupt):
        time.sleep(5)

def test_a_resumed_session_is_shown_whole(served):
    web, bus = served
    started(bus, persistent=True)
    history: list[dict] = [
        {"role": "user", "content": "Lis a.py"},
        {"role": "assistant", "content": "", "tools": [{"name": "cat_file", "arguments": {"path": "a.py"},
                                                        "result": "Erreur : introuvable", "ok": False}]},
        {"role": "assistant", "content": "Le fichier n'existe pas."},
    ]
    bus.dispatch(SESSION_RESUMED, id=4, user="ada", messages=4, last_question="Lis a.py",
                 last_answer="Le fichier n'existe pas.", history=history)
    shown: dict = snapshot(web)
    assert [item["kind"] for item in shown["log"]] == ["user", "tool", "text", "notice"]
    assert shown["log"][1]["status"] == "failed" and shown["state"]["session"] == 4

def test_a_call_is_named_as_a_sentence_says_it():
    assert tool_object("git", {"action": "commit", "branch": "main", "message": "fix"}) == "commit main"
    assert tool_object("run_code", {"language": "python", "code": "print(1)"}) == "python"
    assert tool_object("tree", {"path": "."}) == ""
    assert tool_object("cat_file", {"path": "calc.py"}) == "calc.py"

def test_the_empty_page_suggests_the_files_of_the_project(tmp_path):
    (tmp_path / "old.py").write_text("x")
    (tmp_path / "new.py").write_text("y")
    os.utime(tmp_path / "old.py", (1, 1))
    # Louis's own files, hidden ones and those of the tools are never suggested
    for name in ("louis.db", "louis.log", ".env"):
        (tmp_path / name).write_text("z")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("z")
    hints: dict = project(str(tmp_path))
    assert hints == {"name": tmp_path.name, "changed": [], "recent": ["new.py", "old.py"]}

    # In git: what changed, not what was touched last
    for command in (["init", "-q"], ["add", "old.py"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"]):
        subprocess.run(["git", *command], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "old.py").write_text("changed")
    assert project(str(tmp_path))["changed"] == ["old.py", "new.py"]

def test_history_items_keep_the_calls_without_result():
    items: list[dict] = history_items([
        {"role": "assistant", "content": "Je regarde.", "tools": [{"name": "tree", "arguments": {}, "result": None, "ok": None}]}
    ])
    assert [item["kind"] for item in items] == ["text", "tool"]
    assert items[1]["status"] == "cancelled"

def test_a_shared_page_is_public_until_closed(tmp_path):
    path: str = str(tmp_path / "louis.db")
    db: Database = Database(path)
    user: User = User.get_or_create(db, "ada")
    document: dict = {"v": 1, "kind": "session", "title": "Ma session <script>", "exported_at": "2026-10-06 12:00:00",
                      "session": {"id": None, "user": "ada", "cwd": "/tmp", "created_at": "2026-10-06 12:00:00"},
                      "messages": [{"role": "user", "content": "<b>bonjour</b>", "at": None}], "artifacts": []}
    token: str = store.create(db, user.id, None, document)
    with WebInterface("127.0.0.1", 0, path) as web:
        # Reached by the address of the links, whatever it is (a proxy): no check of the host
        status, headers, body = request(web, "GET", f"/s/{token}", headers={"Host": "share.example.com"})
        assert status == 200 and headers["Content-Security-Policy"].startswith("default-src 'none'")
        assert "<script>" not in body and "&lt;b&gt;bonjour&lt;/b&gt;" in body
        assert request(web, "GET", "/s/AAAAAAAAAAAAAAAAAAAAAA")[0] == 404
        store.revoke(db, user.id, token)
        assert request(web, "GET", f"/s/{token}")[0] == 404
    db.close()

def test_a_readonly_database_is_never_created(tmp_path):
    with pytest.raises(sqlite3.OperationalError):
        Database(str(tmp_path / "absent.db"), readonly=True)
    assert not (tmp_path / "absent.db").exists()

def test_the_log_gives_the_size_of_a_history(caplog):
    import logging
    logger = logging.getLogger("louis")
    logger.setLevel(logging.DEBUG)
    logger.propagate = True
    try:
        log_event(Event(SESSION_RESUMED, {"id": 1, "history": [{}, {}]}))
        log_event(Event(RAG_INDEXED, {"source": "doc", "history": True}))
    finally:
        logger.propagate = False
    assert "history=[2 messages]" in caplog.text and "history=True" in caplog.text
