##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the reasoning loop (/react): its steps, the check of its drafts, what the interfaces, the exports and the
## traces keep of it. The model is a script of replies: no Ollama
##
import json
import pytest
from app.app import App, unsourced
from config.prompt import SYSTEM_PROMPT, REACT_PROMPT, REVISE_PROMPT
from config.settings import settings
from events.event import Event
from events.event_list import REASONING_STEP, REASONING_CHECK, REASONING_ENABLED, REASONING_DISABLED
from events.event_list import CHAT_TEXT, CHAT_TURN_ENDED
from export.document import conversation
from interface.cli import thought_lines
from interface.interface import Interface
from model.model import OllamaModel
from model.model_exception import ModelException
from model.reply import Reply
from monitor.metrics import summarize, load
from monitor.recorder import Recorder
from monitor.report import text
from session.user import User
from tool.tool_call import ToolCall

TREE = ToolCall("tree", {"path": ".", "depth": 1})
OK = (True, [])

def verdict(checks: list[tuple[str, str, bool]], problems: list[str], ok: bool) -> str:
    """ What the model answers when it checks a draft (CRITIQUE) """
    return json.dumps({"checks": [{"claim": claim, "source": source, "holds": holds} for claim, source, holds in checks],
                       "problems": problems, "ok": ok})

class Probe(Interface):
    """ An interface that only keeps what the app tells """
    describes = False

    def __init__(self):
        self.events: list[Event] = []

    def bind(self, bus):
        bus.subscribe(self.events.append)
        return self

    def getUserInput(self) -> str:
        raise EOFError

    def told(self, *names: str) -> list[Event]:
        return [event for event in self.events if event.name in names]

    def ended(self) -> str:
        return self.told(CHAT_TURN_ENDED)[-1].data["reason"]

@pytest.fixture
def louis(folder, monkeypatch, tmp_path):
    """ An app on the anonymous user, recorded in a file of its own, whose model answers make(replies) """
    monkeypatch.setattr(OllamaModel, "_OllamaModel__probe", staticmethod(lambda uri, model: {"tools"}))
    traces = tmp_path / "traces.jsonl"

    def make(replies: list[Reply], verdicts: list[tuple[bool, list[str]]] | None = None, **options) -> tuple[App, Probe]:
        probe = Probe()
        # Nothing that needs more than the scripted model: no NeMo for the guard, no judge in the background
        conf = {**settings, "scribe.model": "", "rag.enabled": False, "sandbox.enabled": False, "guard.enabled": False,
                "eval.enabled": False, **options}
        app = App(conf, SYSTEM_PROMPT, User.anonymous(), probe, Recorder(str(traces), conf))
        sent: list[list[dict]] = []
        answers = iter(replies)

        def chat(messages, *args, **kwargs):
            sent.append(messages)
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return answer
        app.model.chat = chat
        if verdicts is not None:
            checks = iter(verdicts)
            app._App__verify = lambda draft: next(checks)
        app.sent = sent
        return app, probe
    make.traces = traces
    return make

# --- The files a draft names that no tool read ---------------------------------------------------------------------

def tool(content: str, name: str = "cat_file") -> dict:
    return {"role": "tool", "content": content, "tool_name": name}

def called(name: str, **arguments) -> dict:
    return {"role": "assistant", "content": "", "tool_calls": [ToolCall(name, arguments).to_dict()]}

@pytest.mark.parametrize("draft, history, missing", [
    ("src/shop.py définit Cart.", [{"role": "user", "content": "Que fait src/shop.py ?"}], ["src/shop.py"]),
    ("src/shop.py définit total.", [called("cat_file", path="src/shop.py"), tool("def total(): ...")], []),
    ("Regarde src/model/reply.py.", [tool("/model/\n├── model.py\n└── reply.py", "tree")], []),
    ("src/shop.py appelle utils/tax.py.", [called("cat_file", path="src/shop.py"), tool("...")], ["utils/tax.py"]),
    ("Voir https://docs.python.org/3/library/re.html, TVA 1.2, Python 3.13.", [], []),
    ("model/reply.py définit Reply.", [tool("/tests/test_reply.py:3: import x", "search")], ["model/reply.py"]),
])
def test_the_files_no_tool_read_are_found(draft, history, missing):
    assert unsourced(draft, history) == missing

# --- The check of a draft ------------------------------------------------------------------------------------------

def test_a_check_that_finds_nothing_lets_the_draft_go(louis):
    app, _ = louis([Reply(content=verdict([("391", "calcul refait", True)], [], True))])
    assert app._App__verify("17 × 23 = 391.") == OK

def test_a_claim_its_source_does_not_confirm_holds_the_draft_back_even_if_ok(louis):
    app, _ = louis([Reply(content=verdict([("381", "17 × 23 = 391", False)], [], True))])
    assert app._App__verify("17 × 23 = 381.") == (False, ["381 : 17 × 23 = 391"])

@pytest.mark.parametrize("reply", [Reply(content="c'est bon"), Reply(content='{"ok": fal', cut=True),
                                   ModelException("down")])
def test_a_check_that_can_not_be_read_never_holds_the_draft_back(louis, reply):
    app, _ = louis([reply])
    assert app._App__verify("Réponse.") == OK

def test_a_draft_naming_a_file_never_read_is_held_back_without_the_model(louis):
    app, _ = louis([])
    app.session.add("user", "Que fait src/shop.py ?")
    ok, problems = app._App__verify("src/shop.py définit Cart.")
    assert not ok and problems[0].startswith("src/shop.py : aucun outil")
    assert app.sent == []

# --- The loop -----------------------------------------------------------------------------------------------------

def test_each_step_is_told_and_the_answer_shown_once_checked(louis):
    app, probe = louis([Reply(content="Je dois voir le dossier.", tool_calls=[TREE]), Reply(content="Deux fichiers.")], [OK])
    app.reason("Que contient le dossier ?")
    steps = probe.told(REASONING_STEP)
    assert [(step.data["step"], step.data["thought"], step.data["tools"]) for step in steps] == [
        (1, "Je dois voir le dossier.", ["tree"]), (2, "", [])
    ]
    assert [event.data for event in probe.told(REASONING_CHECK)] == [{"attempt": 1, "ok": True, "problems": [],
                                                                       "revise": False}]
    assert [event.data["text"] for event in probe.told(CHAT_TEXT)] == ["Deux fichiers."]
    assert probe.ended() == "done"

def test_the_request_is_told_how_to_reason_but_kept_as_asked(louis):
    app, _ = louis([Reply(content="Faux."), Reply(content="Juste.")], [(False, ["faux"]), OK])
    app.reason("Question ?")
    asked = [message for message in app.sent[1] if message["role"] == "user"]
    assert asked[0]["content"] == "Question ?" + REACT_PROMPT
    assert asked[-1]["content"].startswith(REVISE_PROMPT.split("{")[0])
    assert app.session.history[1]["content"] == "Question ?"

def test_a_rejected_draft_is_written_again_and_never_shown(louis):
    app, probe = louis([Reply(content="Faux."), Reply(content="Juste.")], [(False, ["c'est faux"]), OK])
    app.reason("Question ?")
    checks = [event.data for event in probe.told(REASONING_CHECK)]
    assert [(check["ok"], check["revise"]) for check in checks] == [(False, True), (True, False)]
    assert [event.data["text"] for event in probe.told(CHAT_TEXT)] == ["Juste."]
    # The session keeps the draft and its problems, the trace of how the answer was reached
    assert [message["role"] for message in app.session.history[1:]] == ["user", "assistant", "user", "assistant"]

def test_the_last_answer_goes_with_its_problems_once_the_attempts_are_spent(louis):
    app, probe = louis([Reply(content=f"Essai {i}.") for i in range(3)], [(False, ["non"])] * 3, **{"reason.attempts": 2})
    app.reason("Question ?")
    checks = [event.data for event in probe.told(REASONING_CHECK)]
    assert [check["revise"] for check in checks] == [True, True, False]
    assert [event.data["text"] for event in probe.told(CHAT_TEXT)] == ["Essai 2."]
    assert probe.ended() == "done"

def test_without_verify_the_draft_is_the_answer(louis):
    app, probe = louis([Reply(content="Réponse.")], **{"reason.verify": False})
    app.reason("Question ?")
    assert probe.told(REASONING_CHECK) == []
    assert [event.data["text"] for event in probe.told(CHAT_TEXT)] == ["Réponse."]

def test_cancelled_in_the_check_the_draft_is_neither_shown_nor_kept(louis):
    app, probe = louis([Reply(content="Brouillon.")])
    def interrupt(draft):
        raise KeyboardInterrupt
    app._App__verify = interrupt
    app.reason("Question ?")
    assert probe.ended() == "cancelled"
    assert probe.told(CHAT_TEXT) == []
    assert [message["role"] for message in app.session.history[1:]] == ["user"]

def test_react_switches_the_loop_and_says_so(louis):
    app, probe = louis([])
    app._App__commands.fetch("/react", app)
    assert app.react
    app._App__commands.fetch("/react", app)
    assert not app.react
    assert [event.name for event in probe.told(REASONING_ENABLED, REASONING_DISABLED)] == [REASONING_ENABLED,
                                                                                         REASONING_DISABLED]

# --- What is read of it afterwards --------------------------------------------------------------------------------

def test_the_exports_leave_out_the_rejected_drafts(louis):
    app, _ = louis([Reply(content="Je regarde.", tool_calls=[TREE]), Reply(content="Faux."), Reply(content="Juste.")],
                   [(False, ["faux"]), OK])
    app.reason("Question ?")
    assert [(message["role"], message["content"]) for message in conversation(app.session)] == [
        ("user", "Question ?"), ("assistant", "Je regarde."), ("assistant", "Juste.")
    ]

def test_the_traces_keep_the_steps_the_checks_and_the_answer_given(louis):
    app, _ = louis([Reply(content="Je regarde.", tool_calls=[TREE]), Reply(content="Faux."),
                    Reply(content=verdict([("x", "introuvable", False)], ["faux"], False)), Reply(content="Juste."),
                    Reply(content=verdict([("y", "résultat de tree", True)], [], True))])
    app.reason("Question ?")
    records, _ = load(str(louis.traces))
    kinds = [record["type"] for record in records]
    assert kinds.count("step") == 3 and kinds.count("check") == 2
    turn = next(record for record in records if record["type"] == "turn")
    # The JSON of the checks is no answer, nor are they rounds; the request is kept without REACT_PROMPT
    assert (turn["output"], turn["input"], turn["rounds"]) == ("Juste.", "Question ?", 3)
    assert (turn["react"], turn["steps"], turn["checks"], turn["revised"], turn["left"]) == (True, 3, 2, 1, False)
    assert [record["purpose"] for record in records if record["type"] == "llm"] == ["reply", "reply", "check", "reply", "check"]
    summary = summarize(records)
    assert (summary["reasoning"]["answers"], summary["reasoning"]["revised_rate"]) == (1, 1.0)
    assert "step by step" in text(summary, [], str(louis.traces))

def test_the_step_the_model_numbers_itself_is_shown_without_its_number():
    assert thought_lines("**Étape 1** : je dois voir model/.\n\nPuis lire.") == ["je dois voir model/.", "Puis lire."]
    assert thought_lines("Les étapes 1 et 2 sont faites.") == ["Les étapes 1 et 2 sont faites."]
