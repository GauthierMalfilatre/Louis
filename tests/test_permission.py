##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the permissions: an "always" given to a tool never lets a call that can not be undone go by unseen
##
import pytest
from app.app import App
from config.prompt import SYSTEM_PROMPT
from config.settings import settings
from events.event_bus import EventBus
from events.event_list import TOOL_BEGFOR_PERMISSION, TOOL_GRANT_PERMISSION
from interface.cli import CLI
from model.model import OllamaModel
from session.user import User
from tool.permission import PermissionManager
from tool.risk import Risk, SAFE, REVERSIBLE, IRREVERSIBLE
from tool.tool import Tool
from tool.tool_call import ToolCall

class Acting(Tool):
    """ A tool that asks before it acts, its risk the one given (or a crash, when it can not judge it) """
    def __init__(self, name: str, level: str | None):
        super().__init__(name, "acts", {"type": "object", "properties": {}})
        self.level: str | None = level

    def risk(self, app, **kwargs) -> Risk:
        if self.level is None:
            raise RuntimeError("can not judge")
        return Risk(self.level)

    def handle(self, app, **kwargs) -> str:
        return "OK" if app.permissions.request(self.name, f"{self.name} agit") else "Refusé"

class Answers(CLI):
    """ The CLI, its user answering from a list: what it was asked is kept """
    def __init__(self, answers: list[str]):
        super().__init__()
        self.answers: list[str] = list(answers)
        self.asked: list[str] = []

    def _choose(self, question: str, choices: str) -> str:
        """ As the CLI reads it: a letter that is not among the choices is a no """
        self.asked.append(choices)
        answer: str = self.answers.pop(0)
        return answer if answer in choices else "n"

@pytest.fixture
def louis(folder, monkeypatch, capsys):
    """ An app answered through the CLI, with a tool of each risk """
    monkeypatch.setattr(OllamaModel, "_OllamaModel__probe", staticmethod(lambda uri, model: {"tools"}))

    def make(answers: list[str]) -> tuple[App, Answers]:
        cli = Answers(answers)
        conf = {**settings, "scribe.model": "", "rag.enabled": False, "sandbox.enabled": False, "guard.enabled": False,
                "eval.enabled": False}
        app = App(conf, SYSTEM_PROMPT, User.anonymous(), cli)
        for name, level in (("write", REVERSIBLE), ("push", IRREVERSIBLE), ("broken", None), ("read", SAFE)):
            app._App__toolManager.register(Acting(name, level))
        return app, cli
    return make

def run(app: App, name: str) -> str:
    return app._App__call(ToolCall(name, {}))

def test_every_time_is_told_to_the_interface_while_a_call_can_not_be_undone():
    bus = EventBus()
    told: list[bool] = []
    bus.subscribe(lambda event: told.append(event.data["every_time"]), TOOL_BEGFOR_PERMISSION)
    permissions = PermissionManager(bus)
    permissions.request("git", "commit")
    permissions.strict = True
    permissions.request("git", "push")
    permissions.strict = False
    permissions.request("git", "commit")
    assert told == [False, True, False]

def test_always_lets_the_calls_that_can_be_undone_go(louis):
    app, cli = louis(["a"])
    assert run(app, "write") == "OK" and run(app, "write") == "OK"
    # Asked once, with always among the choices: the second call went without asking
    assert cli.asked == ["yna"]

def test_always_never_lets_a_call_that_can_not_be_undone_go(louis):
    app, cli = louis(["a", "n"])
    # The same tool: always given to it, then a call of it that can not be undone
    app._App__toolManager.get("push").level = REVERSIBLE
    assert run(app, "push") == "OK"
    app._App__toolManager.get("push").level = IRREVERSIBLE
    assert run(app, "push") == "Refusé"
    # Asked again, without always among the choices
    assert cli.asked == ["yna", "yn"]

def test_a_risk_that_can_not_be_judged_is_asked_every_time(louis):
    app, cli = louis(["a", "y"])
    # Always is no choice there: "a" is a no, and the next call is asked again
    assert run(app, "broken") == "Refusé" and run(app, "broken") == "OK"
    assert cli.asked == ["yn", "yn"]

def test_nobody_answering_never_grants(louis):
    bus = EventBus()
    permissions = PermissionManager(bus)
    permissions.strict = True
    assert permissions.request("git", "push") is False
    permissions.strict = False
    # Answered with another id: not the request being asked
    bus.subscribe(lambda event: bus.dispatch(TOOL_GRANT_PERMISSION, id=event.data["id"] + 1, granted=True),
                  TOOL_BEGFOR_PERMISSION)
    assert permissions.request("git", "push") is False
