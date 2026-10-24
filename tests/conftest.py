##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Fixtures of the tests: a project folder the tools work in, its git repository, and what they use of the app
##
import os
import subprocess
import pytest
import utils.path
from config.settings import settings
from tool.seen_files import SeenFiles
from events.event import Event
from events.event_list import TOOL_BEGFOR_PERMISSION, TOOL_GRANT_PERMISSION
from interface.interface import Interface

COAUTHOR = "Louis <louis@example.com>"

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

def git(cwd, *args: str) -> str:
    """ Run git in cwd, as the user would: the state a test starts from, or what it checks after """
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()

@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    """
        The semantic cache is on by default: an app of a test would ask the embedding model of the machine, and store the
        seed. Off unless a test turns it on (tests/test_cache.py)
    """
    monkeypatch.setitem(settings, "cache.enabled", False)

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

class Listener(Interface):
    """ The user of a scripted app: every event it saw, the permissions answered with grant, its messages typed """
    describes = False

    def __init__(self, typed: list[str] | None = None, grant: bool = True):
        self.typed: list[str] = list(typed or [])
        self.grant: bool = grant
        self.events: list[Event] = []

    def bind(self, bus):
        self.bus = bus
        bus.subscribe(self.events.append)
        bus.subscribe(lambda event: bus.dispatch(TOOL_GRANT_PERMISSION, id=event.data["id"], granted=self.grant),
                      TOOL_BEGFOR_PERMISSION)
        return self

    def getUserInput(self) -> str:
        if not self.typed:
            raise EOFError
        return self.typed.pop(0)

    def seen(self, name: str) -> list[dict]:
        """ The data of the events of that name, in their order """
        return [event.data for event in self.events if event.name == name]

@pytest.fixture
def chat(folder, monkeypatch, tmp_path):
    """
        An app whose model answers the replies given, in order (no Ollama): what it was sent is kept in app.sent, its
        calls recorded in app.traces, its interface is app.listener
    """
    from app.app import App
    from config.prompt import SYSTEM_PROMPT
    from model.model import OllamaModel
    from monitor.recorder import Recorder
    from session.user import User
    monkeypatch.setattr(OllamaModel, "_OllamaModel__probe", staticmethod(lambda uri, model: {"tools"}))

    def make(replies: list, *, user=None, listener: Listener | None = None, **options):
        conf = {**settings, "scribe.model": "", "rag.enabled": False, "sandbox.enabled": False, "guard.enabled": False,
                "eval.enabled": False, "hitl.enabled": False, **options}
        traces = tmp_path / f"traces-{len(list(tmp_path.glob('traces-*')))}.jsonl"
        listener = listener or Listener()
        app = App(conf, SYSTEM_PROMPT, user or User.anonymous(), listener, Recorder(str(traces), conf))
        app.traces, app.listener, app.sent = traces, listener, []
        answers = iter(replies)

        def answer(messages, tools=[], images=[], *, on_text=None, schema=None, **kwargs):
            app.sent.append({"messages": [dict(message) for message in messages], "schema": schema,
                             "tools": [tool["function"]["name"] for tool in tools]})
            reply = next(answers)
            if on_text is not None and reply.content and not reply.tool_calls:
                on_text(reply.content)
            return reply
        app.model.chat = answer
        return app
    return make
