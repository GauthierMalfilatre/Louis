##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Fixtures of the tests: a project folder the tools work in, its git repository, and what they use of the app.
## The MCP servers of a test (calc, the fake one of mcp_fake_server.py), and a Louis that runs them
##
import os
import subprocess
import sys
import pytest
import utils.path
from app.app import App
from config.prompt import SYSTEM_PROMPT
from config.settings import settings, CALC_SERVER
from events.event import Event
from events.event_bus import EventBus
from events.event_list import PLAN_PROPOSED, PLAN_DECIDED, TOOL_BEGFOR_PERMISSION, TOOL_GRANT_PERMISSION
from interface.interface import Interface
from model.model import OllamaModel
from model.reply import Reply
from monitor.recorder import Recorder
from session.user import User as Account
from tool.mcp.manager import McpManager
from tool.seen_files import SeenFiles

COAUTHOR = "Louis <louis@example.com>"

FAKE: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_fake_server.py")
CALC: dict = {"name": "calc", "command": sys.executable, "args": [CALC_SERVER]}

class Permissions:
    """ Gives answer to every request, and keeps what was asked: the user, without a terminal """
    def __init__(self, answer: bool = True):
        self.answer: bool = answer
        self.asked: list[str] = []

    def request(self, tool: str, summary: str, preview: str = "", *, every_time: bool = False) -> bool:
        self.asked.append(summary)
        return self.answer

class FakeApp:
    """ What the tools use of the app """
    def __init__(self):
        self.settings: dict = {"git.coauthor": COAUTHOR}
        self.permissions: Permissions = Permissions()
        self.seen_files: SeenFiles = SeenFiles()
        self.knowledge = None
        self.events: EventBus = EventBus()

def git(cwd, *args: str) -> str:
    """ Run git in cwd, as the user would: the state a test starts from, or what it checks after """
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()

def fake(name: str = "fake", *options: str, **extra) -> dict:
    """ The fake MCP server, declared as in the settings """
    return {"name": name, "command": sys.executable, "args": [FAKE, *options], **extra}

class Person(Interface):
    """ The user of Louis: the plans and the permissions it was asked, all approved, and every event """
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

@pytest.fixture(autouse=True)
def no_mcp_servers(monkeypatch):
    """
        An app of a test starts no MCP server, unless the test declares its own: none of the settings, nor uvx, nor
        those of the files of whoever runs the tests
    """
    monkeypatch.setitem(settings, "mcp.servers", [])
    monkeypatch.setitem(settings, "mcp.files", [])

@pytest.fixture
def mcp(folder):
    """ Start the servers given, as Louis does: they are all stopped after the test. None restarts by itself """
    managers: list[McpManager] = []
    def start(*servers: dict, timeout: float = 5.0, start_timeout: float = 5.0, restarts: int = 0, **conf) -> McpManager:
        manager = McpManager({"mcp.servers": list(servers), "mcp.timeout": timeout, "mcp.start_timeout": start_timeout,
                              "mcp.restarts": restarts, **conf})
        managers.append(manager.start())
        return manager
    yield start
    for manager in managers:
        manager.close()

@pytest.fixture
def louis(folder, monkeypatch, tmp_path):
    """ An app with the MCP servers given, its model answering the replies given: the requests it got in app.sent """
    monkeypatch.setattr(OllamaModel, "_OllamaModel__probe", staticmethod(lambda uri, model: {"tools"}))
    apps: list[App] = []

    def make(servers: list[dict], replies: list[Reply], user: Person, **extra) -> App:
        conf = {**settings, "scribe.model": "", "rag.enabled": False, "sandbox.enabled": False, "guard.enabled": False,
                "eval.enabled": False, "hitl.enabled": True, "mcp.servers": servers, **extra}
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

@pytest.fixture
def app() -> FakeApp:
    return FakeApp()

@pytest.fixture
def folder(tmp_path, monkeypatch):
    """ The project the tools work in: the folder Louis started in, found when they are imported """
    work = tmp_path / "work"
    work.mkdir()
    root: str = os.path.realpath(work)
    monkeypatch.chdir(root)
    monkeypatch.setattr(utils.path, "ROOT", root)
    return work

@pytest.fixture
def project(folder, tmp_path):
    """ The project as a git repository with no commit yet, and its origin: a bare repository beside it """
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(folder, "init", "-q", "-b", "main")
    # In the repository only: the global config of whoever runs the tests (signed commits...) stays out
    for key, value in (("user.name", "Tester"), ("user.email", "tester@example.com"), ("commit.gpgsign", "false")):
        git(folder, "config", key, value)
    git(folder, "remote", "add", "origin", str(origin))
    return folder

@pytest.fixture
def repo(project):
    """ The project with a first commit on main, pushed, and a dev branch that only origin has """
    (project / "README.md").write_text("# Projet\n")
    git(project, "add", "README.md")
    git(project, "commit", "-q", "-m", "init")
    git(project, "push", "-q", "-u", "origin", "main")
    git(project, "push", "-q", "origin", "main:dev")
    return project
