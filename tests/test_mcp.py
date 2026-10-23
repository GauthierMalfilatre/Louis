##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the MCP client: the servers of the settings started, their tools discovered and called, and every way a
## server can go wrong told to the model as an error, never a crash of Louis. The servers are real processes: calc,
## the server of Louis, and a fake one (mcp_fake_server.py) that fails on demand
##
import os
import sys
import time
import pytest
from pathlib import Path
from app.app import App
from config.prompt import SYSTEM_PROMPT
from config.settings import settings, CALC_SERVER
from events.event import Event
from events.event_list import MCP_STARTED, MCP_SERVERS, PLAN_PROPOSED, PLAN_DECIDED
from events.event_list import TOOL_BEGFOR_PERMISSION, TOOL_GRANT_PERMISSION
from interface.interface import Interface
from model.model import OllamaModel
from model.reply import Reply
from monitor.recorder import Recorder
from session.user import User as Account
from tool.mcp.manager import McpManager, RUNNING, FAILED, CRASHED, STOPPED
from tool.mcp.tool_mcp import McpTool, tool_name, text_of
from tool.risk import SAFE, REVERSIBLE, IRREVERSIBLE
from tool.tool import failed
from tool.tool_call import ToolCall

FAKE: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_fake_server.py")
CALC: dict = {"name": "calc", "command": sys.executable, "args": [CALC_SERVER]}

def fake(name: str = "fake", *options: str, **extra) -> dict:
    """ The fake server, declared as in the settings """
    return {"name": name, "command": sys.executable, "args": [FAKE, *options], **extra}

@pytest.fixture
def mcp(folder):
    """ Start the servers given, as Louis does: they are all stopped after the test. None restarts by itself """
    managers: list[McpManager] = []
    def start(*servers: dict, timeout: float = 5.0, start_timeout: float = 5.0, restarts: int = 0) -> McpManager:
        manager = McpManager({"mcp.servers": list(servers), "mcp.timeout": timeout, "mcp.start_timeout": start_timeout,
                              "mcp.restarts": restarts})
        managers.append(manager.start())
        return manager
    yield start
    for manager in managers:
        manager.close()

def tools(manager: McpManager) -> dict[str, McpTool]:
    return {tool.name: tool for tool in manager.tools()}

def states(manager: McpManager) -> dict[str, str]:
    return {server.name: server.state for server in manager.servers}

# Discovery

def test_the_tools_of_the_servers_are_discovered_under_their_server_name(mcp):
    found = tools(mcp(CALC, fake()))
    assert {"calc__calculate", "fake__echo", "fake__act", "fake__slow", "fake__crash"} <= set(found)
    calculate = found["calc__calculate"].schema["function"]
    assert calculate["description"].startswith("[MCP calc] Calcule")
    assert calculate["parameters"]["required"] == ["expression"]
    # What the model can not use is taken out of the schema
    assert "$schema" not in found["fake__echo"].schema["function"]["parameters"]

def test_the_tools_of_every_page_are_discovered(mcp):
    found = tools(mcp(fake("fake", "--pages")))
    assert {"fake__echo", "fake__act", "fake__picture"} <= set(found)

def test_a_line_that_is_not_json_does_not_stop_the_server(mcp):
    manager = mcp(fake("fake", "--noise"))
    assert states(manager) == {"fake": RUNNING}

def test_the_name_of_a_tool_is_one_the_model_can_call():
    assert tool_name("my server", "do.it/now") == "my_server__do_it_now"
    assert len(tool_name("s" * 40, "t" * 40)) == 64

# Calls

def test_a_call_gives_the_result_of_the_server(mcp, app):
    calculate = tools(mcp(CALC))["calc__calculate"]
    result = calculate.handle(app, expression="2*(3+4)")
    assert result == "2*(3+4) = 14" and not failed(result)
    # It only reads: nothing asked
    assert app.permissions.asked == []

def test_a_call_that_fails_on_the_server_is_an_error_for_the_model(mcp, app):
    manager = mcp(CALC, fake())
    result = tools(manager)["calc__calculate"].handle(app, expression="1/0")
    assert failed(result) and "division par zéro" in result
    assert tools(manager)["fake__fail"].handle(app) == "Erreur : ça n'a pas marché"
    # The server goes on
    assert tools(manager)["calc__calculate"].handle(app, expression="1+1") == "1+1 = 2"

def test_a_tool_the_server_does_not_have_is_an_error(mcp, app):
    manager = mcp(fake())
    ghost = McpTool(manager.servers[0], {"name": "ghost"})
    result = ghost.handle(app)
    assert failed(result) and "Unknown tool: ghost" in result

def test_a_call_that_takes_too_long_is_an_error_and_the_server_goes_on(mcp, app):
    found = tools(mcp(fake(), timeout=0.3))
    start = time.monotonic()
    result = found["fake__slow"].handle(app, seconds="1")
    assert failed(result) and "n'a pas répondu" in result
    assert time.monotonic() - start < 0.9
    # The fake server ends its call anyway: its late answer is ignored, the next call gets its own
    time.sleep(1)
    assert found["fake__echo"].handle(app, text="encore là") == "encore là"

def test_a_server_that_crashes_is_an_error_then_said_crashed(mcp, app):
    manager = mcp(fake(), CALC)
    found = tools(manager)
    result = found["fake__crash"].handle(app)
    assert failed(result) and "s'est arrêté pendant crash" in result and "Fais sans cet outil" in result
    assert states(manager) == {"fake": CRASHED, "calc": RUNNING}
    after = found["fake__echo"].handle(app, text="là ?")
    assert failed(after) and "ne répond plus" in after
    # Only the tools of the servers that run are offered
    assert all(tool.server == "calc" for tool in manager.tools())

def test_what_is_not_text_is_named_for_the_model(mcp, app):
    assert tools(mcp(fake()))["fake__picture"].handle(app) == "[image image/png]"
    assert text_of({"content": [{"type": "resource", "resource": {"uri": "file:///a", "text": "contenu"}}]}) == "contenu"
    assert text_of({"content": [{"type": "resource_link", "uri": "file:///b", "name": "b"}]}) == "[ressource file:///b] b"
    assert text_of({"content": [], "structuredContent": {"n": 1}}) == '{"n": 1}'

# Servers that do not start

def test_a_server_that_does_not_start_is_left_out_and_the_others_go_on(mcp, app):
    manager = mcp(
        {"name": "missing", "command": "louis-no-such-command"},
        fake("broken", "--fail-init"),
        fake("mute", "--mute"),
        CALC,
        start_timeout=1.0,
    )
    assert states(manager) == {"missing": FAILED, "broken": FAILED, "mute": FAILED, "calc": RUNNING}
    errors = {server["name"]: server["error"] for server in manager.describe()}
    assert "introuvable" in errors["missing"]
    # What it wrote before it stopped tells why
    assert "il manque sa clé d'API" in errors["broken"]
    assert "pas de réponse" in errors["mute"]
    assert set(tools(manager)) == {"calc__calculate"}

@pytest.mark.parametrize("entry, why", [
    ({"command": "x"}, "nom"),
    ({"name": "a"}, "commande"),
    ({"name": "a", "command": "x", "args": "--flag"}, "args"),
    ({"name": "a", "command": "x", "env": {"N": 1}}, "env"),
    ({"name": "a", "command": "x", "risk": "maybe"}, "risk"),
    ("calc", "dict"),
])
def test_a_declaration_that_is_not_valid_is_a_server_that_failed(mcp, entry, why):
    manager = mcp(entry, CALC)
    assert manager.servers[0].state == FAILED and why in manager.servers[0].error
    assert manager.servers[1].state == RUNNING

def test_two_servers_can_not_have_the_same_name(mcp):
    manager = mcp(CALC, CALC)
    assert [server.state for server in manager.servers] == [RUNNING, FAILED]

# Risk and permissions

def test_the_risk_of_a_tool_is_what_the_server_says_unless_the_settings_say_otherwise(mcp):
    found = tools(mcp(fake(), fake("trusted", risk="safe")))
    assert (found["fake__echo"].level, found["fake__gentle"].level, found["fake__act"].level) == (SAFE, REVERSIBLE,
                                                                                                IRREVERSIBLE)
    assert found["trusted__act"].level == SAFE

def test_a_tool_that_acts_asks_first_and_a_refusal_is_told_to_the_model(mcp, app):
    found = tools(mcp(fake()))
    app.permissions.answer = False
    result = found["fake__act"].handle(app)
    assert result.startswith("Refusé") and app.permissions.asked == ["Appel de act sur le serveur MCP fake"]
    app.permissions.answer = True
    assert found["fake__act"].handle(app) == "act : fait"

# What a server gets of Louis

def test_the_server_gets_only_the_environment_it_needs(mcp, app, monkeypatch):
    monkeypatch.setenv("LOUIS_TEST_SECRET", "hunter2")
    env = tools(mcp(fake(env={"GREETING": "salut"})))["fake__env"]
    assert env.handle(app, name="GREETING") == "salut"
    assert env.handle(app, name="LOUIS_TEST_SECRET") == "<absente>"
    assert env.handle(app, name="PATH") == os.environ["PATH"]

def test_the_requests_of_the_server_are_answered(mcp, app, folder):
    result = tools(mcp(fake()))["fake__roots"].handle(app)
    assert Path(folder).resolve().as_uri() in result

def test_close_stops_every_server(mcp):
    manager = mcp(CALC, fake())
    pids = [server.client.pid for server in manager.servers]
    manager.close()
    manager.close()
    assert states(manager) == {"calc": STOPPED, "fake": STOPPED}
    for pid in pids:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)

# In Louis

class Person(Interface):
    """ The user: the plans and the permissions it was asked, all approved """
    describes = False

    def __init__(self):
        self.plans: list[dict] = []
        self.asked: list[str] = []
        self.events: list[Event] = []

    def bind(self, bus):
        self.bus = bus
        bus.subscribe(self.events.append)
        bus.subscribe(self.__on_plan, PLAN_PROPOSED)
        bus.subscribe(self.__on_permission, TOOL_BEGFOR_PERMISSION)
        return self

    def __on_plan(self, event: Event) -> None:
        self.plans.append(event.data)
        self.bus.dispatch(PLAN_DECIDED, id=event.data["id"], approved=True, feedback="")

    def __on_permission(self, event: Event) -> None:
        self.asked.append(event.data["tool"])
        self.bus.dispatch(TOOL_GRANT_PERMISSION, id=event.data["id"], granted=True)

    def getUserInput(self) -> str:
        raise EOFError

    def seen(self, name: str) -> list[dict]:
        return [event.data for event in self.events if event.name == name]

@pytest.fixture
def louis(folder, monkeypatch, tmp_path):
    """ An app with the MCP servers given, its model answering the replies given: the requests it got in app.sent """
    monkeypatch.setattr(OllamaModel, "_OllamaModel__probe", staticmethod(lambda uri, model: {"tools"}))
    apps: list[App] = []

    def make(servers: list[dict], replies: list[Reply], user: Person) -> App:
        conf = {**settings, "scribe.model": "", "rag.enabled": False, "sandbox.enabled": False, "guard.enabled": False,
                "eval.enabled": False, "hitl.enabled": True, "mcp.servers": servers}
        app = App(conf, SYSTEM_PROMPT, Account.anonymous(), user, Recorder(str(tmp_path / "traces.jsonl"), conf))
        apps.append(app)
        answers = iter(replies)
        app.sent, app.offered = [], []
        def chat(messages, tools, *args, **kwargs):
            app.sent.append(messages)
            app.offered.append([tool["function"]["name"] for tool in tools])
            return next(answers)
        app.model.chat = chat
        return app
    yield make
    for app in apps:
        app.close()

def test_the_model_calls_an_mcp_tool_and_answers_with_its_result(louis):
    user = Person()
    call = ToolCall("calc__calculate", {"expression": "1234*5678"})
    app = louis([CALC], [Reply(content="", tool_calls=[call]), Reply(content="1234 × 5678 = 7006652.")], user)
    [started] = user.seen(MCP_STARTED)
    assert started["servers"][0]["state"] == RUNNING
    app._App__answer("Combien font 1234*5678 ?")
    assert "calc__calculate" in app.offered[0]
    # The result is in the session, and the model read it before its answer
    results = [message for message in app.session.history if message["role"] == "tool"]
    assert [message["content"] for message in results] == ["1234*5678 = 7006652"]
    assert any(message.get("content") == "1234*5678 = 7006652" for message in app.sent[1])
    # It only reads: no plan, no question
    assert user.plans == [] and user.asked == []

def test_an_mcp_tool_that_acts_goes_through_the_plan(louis):
    user = Person()
    app = louis([fake()], [Reply(content="J'agis.", tool_calls=[ToolCall("fake__act", {})]), Reply(content="Fait.")],
                user)
    app._App__answer("Agis")
    [plan] = user.plans
    assert [(action["tool"], action["risk"]) for action in plan["actions"]] == [("fake__act", IRREVERSIBLE)]
    # Approved with its plan: the tool asks nothing more
    assert user.asked == []
    assert [message["content"] for message in app.session.history if message["role"] == "tool"] == ["act : fait"]

def test_mcp_lists_the_servers_and_their_tools(louis):
    user = Person()
    app = louis([CALC, {"name": "missing", "command": "louis-no-such-command"}], [], user)
    app._App__commands.fetch("/mcp", app)
    [listed] = user.seen(MCP_SERVERS)
    assert [(server["name"], server["state"]) for server in listed["servers"]] == [("calc", RUNNING), ("missing", FAILED)]
    assert [tool["name"] for tool in listed["servers"][0]["tools"]] == ["calc__calculate"]

def test_the_servers_stop_when_louis_closes(louis):
    app = louis([CALC], [], Person())
    pid = app.mcp.servers[0].client.pid
    app.close()
    assert app.mcp.servers[0].state == STOPPED
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
