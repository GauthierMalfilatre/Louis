##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the HTTP transport of MCP (Streamable HTTP), against a fake server run in the test: its answers in JSON or
## in a stream of events (with the progress, and requests of its own), its session, its token, a session it forgot,
## a server that does not answer, and the end of the session when Louis closes
##
import io
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from events.event_list import MCP_PROGRESS
from tool.mcp.manager import RUNNING, FAILED, CRASHED, STOPPED
from tool.mcp.transport_http import events
from tool.tool import failed

TOOLS: list[dict] = [{"name": name, "annotations": {"readOnlyHint": True}, "inputSchema": {"type": "object"}}
                     for name in ("echo", "progress", "ping_me")]

class FakeServer(ThreadingHTTPServer):
    """ What the fake server was sent, and how it behaves """
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.token: str | None = None          # the Authorization it wants, None for any
        self.stream: bool = False              # whether it has a stream of its own (GET), that adds a tool
        self.tools: list[dict] = list(TOOLS)
        self.sessions: set[str] = set()
        self.initialized: int = 0
        self.received: list[dict] = []         # the messages POSTed, with their headers
        self.deleted: list[str] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/mcp"

class Handler(BaseHTTPRequestHandler):
    server: FakeServer

    def log_message(self, *args) -> None:
        pass

    def send(self, code: int, body: dict | None = None, **headers: str) -> None:
        data: bytes = json.dumps(body).encode() if body is not None else b""
        self.send_response(code)
        if body is not None:
            self.send_header("Content-Type", "application/json")
        for key, value in headers.items():
            self.send_header(key.replace("_", "-"), value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def stream(self, *messages: dict) -> None:
        """ An answer as a stream of events, one message each """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for message in messages:
            self.wfile.write(f"event: message\ndata: {json.dumps(message)}\n\n".encode())
            self.wfile.flush()
            time.sleep(0.05)

    def do_POST(self) -> None:
        message: dict = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        # The names of the headers in lower case: they are, for HTTP
        self.server.received.append({"message": message, "headers": {key.lower(): value for key, value in self.headers.items()}})
        if self.server.token is not None and self.headers.get("Authorization") != self.server.token:
            return self.send(401)
        method, number = message.get("method"), message.get("id")
        if method == "initialize":
            self.server.initialized += 1
            session: str = f"s-{self.server.initialized}"
            self.server.sessions.add(session)
            return self.send(200, {"jsonrpc": "2.0", "id": number, "result": {
                "protocolVersion": message["params"]["protocolVersion"], "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "fake-http", "version": "0"}}}, Mcp_Session_Id=session)
        if self.headers.get("Mcp-Session-Id") not in self.server.sessions:
            return self.send(404)
        if number is None or method is None:
            # A notification, or the answer of the client to a request of the server
            return self.send(202)
        if method == "tools/list":
            return self.send(200, {"jsonrpc": "2.0", "id": number, "result": {"tools": self.server.tools}})
        name, arguments = message["params"]["name"], message["params"].get("arguments") or {}
        done: dict = {"jsonrpc": "2.0", "id": number}
        if name == "echo":
            return self.send(200, {**done, "result": {"content": [{"type": "text", "text": arguments.get("text", "")}]}})
        if name == "progress":
            token = message["params"]["_meta"]["progressToken"]
            steps = [{"jsonrpc": "2.0", "method": "notifications/progress",
                      "params": {"progressToken": token, "progress": step, "total": 3, "message": f"étape {step}"}}
                     for step in (1, 2, 3)]
            return self.stream(*steps, {**done, "result": {"content": [{"type": "text", "text": "fini"}]}})
        if name == "ping_me":
            return self.stream({"jsonrpc": "2.0", "id": "srv-1", "method": "ping"},
                               {**done, "result": {"content": [{"type": "text", "text": "pong demandé"}]}})
        self.send(200, {**done, "error": {"code": -32602, "message": f"Unknown tool: {name}"}})

    def do_GET(self) -> None:
        if not self.server.stream:
            return self.send(405)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(b": the stream of the server\n\n")
        self.server.tools.append({"name": "added", "inputSchema": {"type": "object"}})
        self.wfile.write(f"data: {json.dumps({'jsonrpc': '2.0', 'method': 'notifications/tools/list_changed'})}\n\n".encode())
        self.wfile.flush()
        time.sleep(0.5)

    def do_DELETE(self) -> None:
        session: str = self.headers.get("Mcp-Session-Id", "")
        self.server.deleted.append(session)
        self.server.sessions.discard(session)
        self.send(200)

@pytest.fixture
def server():
    """ The fake server, listening on a free port while the test runs """
    fake: FakeServer = FakeServer()
    thread = threading.Thread(target=fake.serve_forever, daemon=True)
    thread.start()
    yield fake
    fake.shutdown()
    fake.server_close()

def web(url: str, **extra) -> dict:
    return {"name": "web", "url": url, **extra}

def tools(manager) -> dict:
    return {tool.name: tool for tool in manager.tools()}

# Talking to it

def test_a_server_at_an_address_is_discovered_and_called(server, mcp, app):
    manager = mcp(web(server.url))
    described = manager.describe()[0]
    assert (described["state"], described["transport"], described["command"]) == (RUNNING, "http", server.url)
    assert set(tools(manager)) == {"web__echo", "web__progress", "web__ping_me"}
    assert tools(manager)["web__echo"].handle(app, text="bonjour") == "bonjour"
    # After initialize, every message names the session and the version agreed
    last = server.received[-1]["headers"]
    assert (last["mcp-session-id"], last["mcp-protocol-version"]) == ("s-1", "2025-06-18")
    assert "text/event-stream" in last["accept"] and "application/json" in last["accept"]

def test_an_answer_may_come_in_a_stream_with_the_progress_before_it(server, mcp, app):
    told: list[dict] = []
    app.events.subscribe(lambda event: told.append(event.data), MCP_PROGRESS)
    assert tools(mcp(web(server.url)))["web__progress"].handle(app) == "fini"
    assert [step["message"] for step in told] == ["étape 1", "étape 2", "étape 3"]

def test_a_request_of_the_server_in_a_stream_is_answered(server, mcp, app):
    assert tools(mcp(web(server.url)))["web__ping_me"].handle(app) == "pong demandé"
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not any(sent["message"].get("id") == "srv-1" for sent in server.received):
        time.sleep(0.05)
    [answer] = [sent["message"] for sent in server.received if sent["message"].get("id") == "srv-1"]
    assert answer == {"jsonrpc": "2.0", "id": "srv-1", "result": {}}

def test_a_tool_the_server_does_not_have_is_an_error(server, mcp, app):
    manager = mcp(web(server.url))
    from tool.mcp.tool_mcp import McpTool
    result = McpTool(manager.servers[0], {"name": "ghost"}).handle(app)
    assert failed(result) and "Unknown tool: ghost" in result

# Its token

def test_the_token_of_the_environment_goes_in_the_headers(server, mcp, app, monkeypatch):
    server.token = "Bearer secret"
    monkeypatch.setenv("LOUIS_TEST_TOKEN", "secret")
    monkeypatch.delenv("LOUIS_TEST_ABSENT", raising=False)
    manager = mcp(web(server.url, headers={"Authorization": "Bearer ${LOUIS_TEST_TOKEN}"}),
                  web(server.url, name="wrong", headers={"Authorization": "Bearer nope"}),
                  web(server.url, name="unset", headers={"Authorization": "Bearer ${LOUIS_TEST_ABSENT}"}))
    assert [server.state for server in manager.servers] == [RUNNING, FAILED, FAILED]
    assert "HTTP 401" in manager.server("wrong").error and "token" in manager.server("wrong").error
    assert "LOUIS_TEST_ABSENT n'est pas définie" in manager.server("unset").error
    # Never in what /mcp shows
    assert "secret" not in json.dumps(manager.describe())

# What goes wrong

def test_a_session_the_server_forgot_is_started_again_at_the_next_call(server, mcp, app):
    manager = mcp(web(server.url), restarts=1)
    echo = tools(manager)["web__echo"]
    server.sessions.clear()
    result = echo.handle(app, text="là ?")
    assert failed(result) and manager.servers[0].state == CRASHED and "session" in manager.servers[0].why
    # Initialized again: a new session
    assert echo.handle(app, text="de retour") == "de retour"
    assert server.initialized == 2 and manager.servers[0].state == RUNNING

def test_a_server_that_does_not_answer_is_an_error_never_a_crash(server, mcp, app):
    url: str = server.url
    absent = mcp(web("http://127.0.0.1:9/mcp"))
    assert absent.servers[0].state == FAILED and "ne répond pas" in absent.servers[0].error
    manager = mcp(web(url))
    server.shutdown()
    server.server_close()
    result = tools(manager)["web__echo"].handle(app, text="là ?")
    assert failed(result) and "ne répond pas" in result and manager.servers[0].state == CRASHED

@pytest.mark.parametrize("entry, why", [
    ({"type": "sse", "url": "http://127.0.0.1:1/sse"}, "sse"),
    ({"type": "http", "url": "ftp://example.com"}, "http://"),
    ({"type": "carrier-pigeon", "url": "http://127.0.0.1:1"}, "type"),
    ({"url": "http://127.0.0.1:1", "headers": {"X-Count": 1}}, "headers"),
])
def test_a_declaration_of_an_address_that_is_not_valid_is_a_server_that_failed(mcp, entry, why):
    manager = mcp({"name": "web", **entry})
    assert manager.servers[0].state == FAILED and why in manager.servers[0].error

# Its own stream, and its end

def test_the_stream_of_the_server_tells_its_tools_changed(server, mcp):
    server.stream = True
    manager = mcp(web(server.url))
    deadline = time.monotonic() + 3
    changes: list = []
    while time.monotonic() < deadline and not changes:
        changes = manager.refresh()
        time.sleep(0.05)
    assert [(changed.name, change) for changed, change in changes] == [("web", "tools")]
    assert "web__added" in tools(manager)

def test_closing_ends_the_session_on_the_server(server, mcp):
    manager = mcp(web(server.url))
    manager.close()
    assert server.deleted == ["s-1"] and manager.servers[0].state == STOPPED

def test_the_messages_of_a_stream_of_events():
    stream = io.BytesIO(b": comment\nevent: message\ndata: {\"a\": 1}\n\ndata: [{\"b\": 2},\ndata: {\"c\": 3}]\n\n"
                        b"data: not json\n\nid: 7\ndata: {\"d\": 4}")
    assert list(events(stream)) == [{"a": 1}, {"b": 2}, {"c": 3}, {"d": 4}]
