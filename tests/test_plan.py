##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the human in the loop: a reply with a risky call is suspended, its plan shown, and its calls run only once
## the user approved it. The model is a script of replies, the user the answers given
##
import pytest
from app.app import App
from app.constants import REFUSED_PLAN
from config.prompt import SYSTEM_PROMPT
from config.settings import settings
from events.event import Event
from events.event_list import PLAN_PROPOSED, PLAN_DECIDED, TOOL_BEGFOR_PERMISSION, TOOL_GRANT_PERMISSION
from events.event_list import CHAT_TURN_ENDED
from interface.interface import Interface
from model.model import OllamaModel
from model.reply import Reply
from session.user import User as Account
from tool.permission import PermissionManager
from events.event_bus import EventBus
from tool.risk import Risk, REVERSIBLE, IRREVERSIBLE
from tool.tool import Tool
from tool.tool_call import ToolCall

class Acting(Tool):
    """ A tool that asks before it acts, of the risk given: what it ran is kept """
    def __init__(self, name: str, level: str):
        super().__init__(name, "acts", {"type": "object", "properties": {}})
        self.level: str = level
        self.ran: int = 0

    def risk(self, app, **kwargs) -> Risk:
        return Risk(self.level, f"{self.name} agit", "", f"diff de {self.name}")

    def handle(self, app, **kwargs) -> str:
        if not app.permissions.request(self.name, f"{self.name} agit"):
            return "Refusé : pas autorisé."
        self.ran += 1
        return "OK"

class Person(Interface):
    """ The user: the plans and the permissions it was asked, and how it answers them (None: it does not) """
    describes = False

    def __init__(self, plan: tuple[bool, str] | None = (True, ""), grant: bool = True):
        self.plan, self.grant = plan, grant
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
        if self.plan is not None:
            approved, feedback = self.plan
            self.bus.dispatch(PLAN_DECIDED, id=event.data["id"], approved=approved, feedback=feedback)

    def __on_permission(self, event: Event) -> None:
        self.asked.append(event.data["tool"])
        self.bus.dispatch(TOOL_GRANT_PERMISSION, id=event.data["id"], granted=self.grant)

    def getUserInput(self) -> str:
        raise EOFError

    def ended(self) -> str:
        return [event for event in self.events if event.name == CHAT_TURN_ENDED][-1].data["reason"]

@pytest.fixture
def louis(folder, monkeypatch):
    """ An app with a reversible tool (write) and one that can not be undone (push), its model answering replies """
    monkeypatch.setattr(OllamaModel, "_OllamaModel__probe", staticmethod(lambda uri, model: {"tools"}))

    def make(replies: list[Reply], user: Person, **options) -> tuple[App, dict[str, Acting]]:
        conf = {**settings, "scribe.model": "", "rag.enabled": False, "sandbox.enabled": False, "guard.enabled": False,
                "eval.enabled": False, "hitl.enabled": True, **options}
        app = App(conf, SYSTEM_PROMPT, Account.anonymous(), user)
        tools: dict[str, Acting] = {"write": Acting("write", REVERSIBLE), "push": Acting("push", IRREVERSIBLE)}
        for tool in tools.values():
            app._App__toolManager.register(tool)
        answers = iter(replies)
        app.sent = []
        def chat(messages, *args, **kwargs):
            app.sent.append(messages)
            return next(answers)
        app.model.chat = chat
        return app, tools
    return make

BOTH = [ToolCall("write", {"path": "a.py"}), ToolCall("push", {})]

def results(app: App) -> list[str]:
    return [message["content"] for message in app.session.history if message["role"] == "tool"]

def test_a_risky_reply_waits_for_its_plan_then_runs_without_asking_again(louis):
    user = Person(plan=(True, ""))
    app, tools = louis([Reply(content="J'écris puis je pousse.", tool_calls=BOTH), Reply(content="Fait.")], user)
    app._App__answer("Pousse mon travail")
    [plan] = user.plans
    assert plan["intent"] == "J'écris puis je pousse."
    assert [(action["tool"], action["risk"]) for action in plan["actions"]] == [("write", REVERSIBLE),
                                                                                ("push", IRREVERSIBLE)]
    assert plan["actions"][1]["preview"] == "diff de push"
    assert (tools["write"].ran, tools["push"].ran) == (1, 1)
    # The user said yes to the whole plan: no tool asked again
    assert user.asked == []
    assert user.ended() == "done"

def test_a_refused_plan_runs_none_of_its_calls_and_tells_the_model_why(louis):
    user = Person(plan=(False, "fais d'abord une branche"))
    app, tools = louis([Reply(content="Je pousse.", tool_calls=BOTH), Reply(content="D'accord, je ne pousse pas.")],
                       user)
    app._App__answer("Pousse mon travail")
    assert (tools["write"].ran, tools["push"].ran) == (0, 0) and user.asked == []
    told: list[str] = results(app)
    assert len(told) == 2 and all(result.startswith(REFUSED_PLAN) for result in told)
    assert "fais d'abord une branche" in told[0]
    # The model reads it before its next reply
    assert any("fais d'abord une branche" in (message.get("content") or "") for message in app.sent[1])
    assert user.ended() == "done"

def test_a_reply_below_the_level_needs_no_plan_each_tool_asks_as_usual(louis):
    user = Person()
    app, tools = louis([Reply(content="", tool_calls=[ToolCall("write", {})]), Reply(content="Fait.")], user)
    app._App__answer("Écris")
    assert user.plans == [] and user.asked == ["write"] and tools["write"].ran == 1

def test_the_level_can_ask_a_plan_for_what_can_be_undone_too(louis):
    user = Person()
    app, tools = louis([Reply(content="", tool_calls=[ToolCall("write", {})]), Reply(content="Fait.")], user,
                       **{"hitl.level": REVERSIBLE})
    app._App__answer("Écris")
    assert len(user.plans) == 1 and user.asked == [] and tools["write"].ran == 1

def test_without_hitl_the_tools_ask_as_before(louis):
    user = Person()
    app, tools = louis([Reply(content="", tool_calls=BOTH), Reply(content="Fait.")], user, **{"hitl.enabled": False})
    app._App__answer("Pousse")
    assert user.plans == [] and user.asked == ["write", "push"]

def test_nobody_answering_the_plan_runs_nothing(louis):
    user = Person(plan=None)
    app, tools = louis([Reply(content="", tool_calls=BOTH), Reply(content="Je ne peux pas.")], user)
    app._App__answer("Pousse")
    assert (tools["write"].ran, tools["push"].ran) == (0, 0)
    assert all(result.startswith(REFUSED_PLAN) for result in results(app))

def test_cancelled_while_the_plan_is_asked_every_call_gets_its_answer(louis):
    user = Person(plan=None)
    def interrupt(event: Event) -> None:
        raise KeyboardInterrupt
    app, tools = louis([Reply(content="", tool_calls=BOTH)], user)
    app.events.subscribe(interrupt, PLAN_PROPOSED)
    app._App__answer("Pousse")
    assert user.ended() == "cancelled" and (tools["write"].ran, tools["push"].ran) == (0, 0)
    assert len(results(app)) == 2

def test_with_react_the_plan_tells_the_thought_of_the_step(louis):
    user = Person()
    app, tools = louis([Reply(content="Je dois pousser la branche.", tool_calls=[ToolCall("push", {})]),
                        Reply(content="Poussée.")], user, **{"reason.verify": False})
    app.reason("Pousse")
    assert user.plans[0]["intent"] == "Je dois pousser la branche." and tools["push"].ran == 1

def test_only_the_first_answer_to_a_plan_counts():
    bus = EventBus()
    permissions = PermissionManager(bus)
    def answer(event: Event) -> None:
        bus.dispatch(PLAN_DECIDED, id=event.data["id"], approved=False, feedback=" non ")
        bus.dispatch(PLAN_DECIDED, id=event.data["id"], approved=True, feedback="")
    bus.subscribe(answer, PLAN_PROPOSED)
    assert permissions.propose("but", []) == (False, "non")
