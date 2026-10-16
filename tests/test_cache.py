##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the semantic cache: when two questions are the same one, what is stored, and the app that answers from it
##
import hashlib
import json
import numpy as np
import pytest
from app.app import App
from cache.rules import same_specifics, timely, situated, why_not
from cache.semantic_cache import SemanticCache
from cache.store import Store
from config.prompt import SYSTEM_PROMPT
from config.settings import settings
from events.event import Event
from events.event_bus import EventBus
from events.event_list import CHAT_TURN_STARTED, CHAT_TURN_ENDED, CHAT_REPLY, CHAT_TEXT, TOOL_CALL_ENDED
from events.event_list import GUARD_TRIGGERED, REASONING_CHECK, RAG_INDEXED, RAG_FORGOTTEN
from events.event_list import CACHE_LOOKUP, CACHE_HIT, CACHE_STORED, CACHE_CLEARED, CACHE_STATS, MODEL_CALL
from interface.interface import Interface
from model.model import OllamaModel
from model.reply import Reply
from monitor.recorder import Recorder
from rag.embedder import Embedder, EmbedError
from rag.reranker import Reranker, RerankError
from session.user import User

QUESTION   = "Comment lire un fichier JSON en Python ?"
PARAPHRASE = "Comment on lit un fichier JSON avec Python ?"
OTHER      = "Comment écrire un fichier JSON en Python ?"
ANSWER     = "Avec json.load(f), le fichier ouvert en lecture."

def noise(text: str, size: int = 16) -> np.ndarray:
    """ A vector of its own for each text: far from the others """
    seed: int = int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], "little")
    return np.random.default_rng(seed).normal(size=size)

# The texts the tests ask about, near or far in meaning: PARAPHRASE ~0.99 from QUESTION, OTHER ~0.8
BASE: np.ndarray = noise("base")
VECTORS: dict[str, np.ndarray] = {
    QUESTION  : BASE,
    PARAPHRASE: BASE + 0.1 * noise("paraphrase"),
    OTHER     : BASE + 0.8 * noise("other"),
}

def meaning(text: str) -> list[float]:
    """ What the fake embedding model reads of a text: the same question in other numbers is the same sentence """
    known: np.ndarray | None = next((vector for key, vector in VECTORS.items() if key == text), None)
    return list(known if known is not None else BASE if "17" in text else noise(text))

class FakeEmbedder:
    """ An embedding model without Ollama: down raises as Ollama stopped would """
    model: str = "fake-embed"

    def __init__(self, down: bool = False):
        self.down: bool = down

    def query(self, text: str) -> list[float]:
        if self.down:
            raise EmbedError("Ollama ne répond pas")
        return meaning(text)

class FakeReranker:
    """ A cross-encoder without fastembed: the pairs in rejected are not the same question, down raises as it missing would """
    model: str = "fake-rerank"

    def __init__(self, rejected: set[tuple[str, str]] = frozenset(), down: bool = False):
        self.rejected = rejected
        self.down: bool = down

    def score(self, query: str, texts: list[str]) -> list[float]:
        if self.down:
            raise RerankError("le reranking a besoin de fastembed")
        return [0.05 if (query, text) in self.rejected else 0.9 for text in texts]

class Clock:
    """ The time, moved by the tests """
    def __init__(self):
        self.now: float = 1_000_000.0

    def __call__(self) -> float:
        return self.now

@pytest.fixture
def cache(tmp_path):
    """ A cache on its own bus, whose events are kept: make(**options) """
    def make(embedder=None, **options) -> SemanticCache:
        bus = EventBus()
        told: list[Event] = []
        bus.subscribe(told.append)
        clock = Clock()
        found = SemanticCache(bus, Store(str(tmp_path / "cache.db")), embedder or FakeEmbedder(), clock=clock,
                              **{"enabled": True, "threshold": 0.92, "reranker": FakeReranker(), **options})
        found.bus, found.told, found.clock = bus, told, clock
        return found
    return make

def ask(cache: SemanticCache, question: str, *, model: str = "qwen", prompt: str = "prompt", first: bool = True,
        answer: str | None = ANSWER, tools: list[tuple[str, bool]] = (), reason: str = "done", events=()):
    """ A turn of the app, as the bus tells it: looked up, then answered by the model unless the cache did """
    bus: EventBus = cache.bus
    bus.dispatch(CHAT_TURN_STARTED)
    hit = cache.lookup(question, model=model, prompt=prompt, first=first)
    if hit is None:
        for name, ok in tools:
            bus.dispatch(TOOL_CALL_ENDED, name=name, producer="model", ok=ok, result="...", duration=0.1)
        for name, data in events:
            bus.dispatch(name, **data)
        if answer is not None:
            bus.dispatch(CHAT_REPLY, content=answer, tools=[])
    bus.dispatch(CHAT_TURN_ENDED, reason=reason, message=None)
    return hit

def told(cache: SemanticCache, name: str) -> list[dict]:
    return [event.data for event in cache.told if event.name == name]

# --- When two questions are the same one ---------------------------------------------------------------------------

@pytest.mark.parametrize("first, second, same", [
    ("Combien font 17 × 23 ?", "Combien font 17 x 23 ?", True),
    ("Combien font 17 × 23 ?", "Combien font 17 × 24 ?", False),
    ("Que fait config.py ?", "Que fait settings.py ?", False),
    ("Que fait Config.py ?", "que fait config.py", True),
    ("À quoi sert load_config ?", "À quoi sert load_settings ?", False),
    ("Que fait `run` ?", "Que fait `stop` ?", False),
    ("Explique ContextWindow", "Explique ToolManager", False),
    ("Qu'est-ce qu'une closure ?", "C'est quoi une closure ?", True),
    ("Arrondir 0,5", "Arrondir 0.5", True),
])
def test_two_questions_are_the_same_only_with_the_same_details(first, second, same):
    assert same_specifics(first, second) is same

@pytest.mark.parametrize("question, expected", [
    ("Quel jour sommes-nous ?", True), ("Quelle est la dernière version de Python ?", True),
    ("What time is it now?", True), ("Qu'est-ce qu'une closure ?", False), ("Comment trier une liste ?", False),
])
def test_what_depends_on_the_time_is_found(question, expected):
    assert timely(question) is expected

@pytest.mark.parametrize("question, expected", [
    ("Que fait ce fichier ?", True), ("Résume ce projet", True), ("Explain this repo", True),
    ("Comment trier une liste ?", False),
])
def test_what_depends_on_the_project_is_found(question, expected):
    assert situated(question) is expected

def test_only_the_first_message_is_looked_up_with_the_scope_first():
    assert why_not(QUESTION, False, "first") == "followup"
    assert why_not(QUESTION, False, "any") is None
    assert why_not(QUESTION, True, "first") is None

# --- Looked up, stored, given again --------------------------------------------------------------------------------

def test_an_answer_is_given_again_to_a_question_that_means_the_same(cache):
    found = cache()
    assert ask(found, QUESTION) is None
    assert len(told(found, CACHE_STORED)) == 1
    hit = ask(found, PARAPHRASE)
    assert hit is not None and hit.answer == ANSWER and hit.question == QUESTION and hit.score >= 0.92
    assert told(found, CACHE_LOOKUP)[-1]["hit"] is True
    assert found.stats()["hits"] == 1 and found.stats()["served"] == 1 and found.stats()["hit_rate"] == 0.5

def test_a_question_far_enough_is_answered_by_the_model(cache):
    found = cache()
    ask(found, QUESTION)
    assert ask(found, OTHER) is None
    assert told(found, CACHE_LOOKUP)[-1]["score"] < 0.92

def test_the_same_sentence_with_other_numbers_is_never_given_the_answer(cache):
    found = cache()
    ask(found, "Combien font 17 × 23 ?", answer="391")
    assert ask(found, "Combien font 17 × 24 ?", answer="408") is None
    assert ask(found, "Combien font 17 x 23 ?").answer == "391"

@pytest.mark.parametrize("scope", [{"model": "llama"}, {"prompt": "another prompt"}])
def test_another_model_or_prompt_never_gets_the_answer(cache, scope):
    found = cache()
    ask(found, QUESTION)
    assert ask(found, PARAPHRASE, **scope) is None

def test_the_users_never_get_each_other_answers(cache, tmp_path):
    alice = cache(user_id=1)
    ask(alice, QUESTION)
    bob = cache(user_id=2)
    assert ask(bob, PARAPHRASE) is None
    assert ask(cache(user_id=1), PARAPHRASE) is not None

def test_an_answer_too_old_is_never_given_again(cache):
    found = cache(ttl=3600)
    ask(found, QUESTION)
    found.clock.now += 3601
    assert ask(found, PARAPHRASE) is None

def test_the_answers_served_least_lately_are_dropped_first(cache):
    found = cache(most=2)
    for question in ("Qu'est-ce qu'une closure ?", "Qu'est-ce qu'un décorateur ?", "Qu'est-ce qu'un générateur ?"):
        found.clock.now += 1
        ask(found, question)
    assert found.stats()["entries"] == 2
    assert ask(found, "Qu'est-ce qu'une closure ?") is None

# --- What is never stored ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("turn", [
    {"tools": [("cat_file", True)]},
    {"tools": [("search_knowledge", False)]},
    {"reason": "cancelled"},
    {"reason": "length"},
    {"answer": None},
    {"events": [(GUARD_TRIGGERED, {"stage": "output", "action": "refused", "rails": ["x"], "content": "Non."})]},
    {"events": [(REASONING_CHECK, {"attempt": 3, "ok": False, "problems": ["faux"], "revise": False})]},
])
def test_an_answer_not_safe_to_give_again_is_never_stored(cache, turn):
    found = cache()
    ask(found, QUESTION, **turn)
    assert told(found, CACHE_STORED) == []

def test_an_answer_of_the_knowledge_base_is_stored(cache):
    found = cache()
    ask(found, QUESTION, tools=[("search_knowledge", True)])
    assert told(found, CACHE_STORED) == [{"id": 1, "tools": ["search_knowledge"]}]

@pytest.mark.parametrize("question, first, reason", [
    (QUESTION, False, "followup"), ("Quel jour sommes-nous ?", True, "timely"), ("Que fait ce fichier ?", True, "project"),
])
def test_a_question_the_cache_may_not_answer_is_not_looked_up_nor_stored(cache, question, first, reason):
    found = cache()
    ask(found, question, first=first)
    assert [(lookup["hit"], lookup["score"], lookup["reason"]) for lookup in told(found, CACHE_LOOKUP)] == \
        [(False, None, reason)]
    assert told(found, CACHE_STORED) == []

def test_nothing_is_looked_up_nor_stored_while_it_is_off(cache):
    found = cache(enabled=False)
    ask(found, QUESTION)
    assert told(found, CACHE_LOOKUP) == [] and told(found, CACHE_STORED) == []

def test_an_embedding_model_down_never_fails_the_turn(cache):
    found = cache(FakeEmbedder(down=True))
    assert ask(found, QUESTION) is None
    assert told(found, CACHE_LOOKUP)[0]["reason"] == "embed" and told(found, CACHE_STORED) == []

def test_a_question_close_in_meaning_is_given_the_answer_only_if_the_reranker_finds_it_the_same(cache):
    found = cache(reranker=FakeReranker({(PARAPHRASE, QUESTION)}))
    ask(found, QUESTION)
    assert ask(found, PARAPHRASE) is None
    assert told(found, CACHE_LOOKUP)[-1]["score"] >= 0.92

def test_the_answer_is_verified_by_the_reranker(cache):
    found = cache()
    ask(found, QUESTION)
    assert ask(found, PARAPHRASE).verified == 0.9

def test_without_a_reranker_nothing_is_given_but_the_answers_are_stored(cache):
    found = cache(reranker=FakeReranker(down=True))
    ask(found, QUESTION)
    assert ask(found, PARAPHRASE) is None
    assert found.stats()["entries"] == 2
    assert ask(cache(), PARAPHRASE) is not None

def test_without_verify_the_meaning_is_enough(cache):
    found = cache(reranker=None, verify=False)
    ask(found, QUESTION)
    hit = ask(found, PARAPHRASE)
    assert hit is not None and hit.verified is None

def test_an_answer_stored_without_the_guard_is_never_given_with_it(cache):
    ask(cache(guard=False), QUESTION)
    assert ask(cache(guard=True), PARAPHRASE) is None

# --- Forgotten -----------------------------------------------------------------------------------------------------

def test_the_answers_of_the_knowledge_base_are_forgotten_when_it_changes(cache):
    found = cache()
    ask(found, QUESTION, tools=[("search_knowledge", True)])
    ask(found, "Qu'est-ce qu'une closure ?")
    found.bus.dispatch(RAG_INDEXED, source="docs", updated=0, removed=0)
    assert found.stats()["entries"] == 2
    found.bus.dispatch(RAG_FORGOTTEN, source="docs", chunks=12)
    assert found.stats()["entries"] == 1
    assert told(found, CACHE_CLEARED) == [{"scope": "rag", "entries": 1}]

def test_the_last_answer_served_can_be_forgotten(cache):
    found = cache()
    assert found.forget_last() == 0
    ask(found, QUESTION)
    ask(found, PARAPHRASE)
    assert found.forget_last() == 1
    assert ask(found, PARAPHRASE) is None

def test_clear_removes_the_answers_of_the_user_only(cache):
    ask(cache(user_id=1), QUESTION)
    found = cache(user_id=2)
    ask(found, QUESTION)
    assert found.clear() == 1
    assert cache(user_id=1).stats()["entries"] == 1

def test_nothing_is_written_on_the_disk_before_an_answer_is_stored(cache, tmp_path):
    found = cache()
    ask(found, QUESTION, reason="cancelled")
    found.stats()
    assert not (tmp_path / "cache.db").exists()

# --- The app -------------------------------------------------------------------------------------------------------

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

@pytest.fixture
def louis(folder, monkeypatch, tmp_path):
    """ An app with the cache on, whose model answers the replies given, and whose embedding model is FakeEmbedder """
    monkeypatch.setattr(OllamaModel, "_OllamaModel__probe", staticmethod(lambda uri, model: {"tools"}))
    monkeypatch.setattr(Embedder, "query", lambda self, text: meaning(text))
    # Never fastembed: the tests run where it is not installed
    monkeypatch.setattr(Reranker, "score", lambda self, query, texts: [0.9] * len(texts))
    monkeypatch.setenv("LOUIS_CACHE", str(tmp_path / "cache.db"))
    traces = tmp_path / "traces.jsonl"

    def make(replies: list[Reply], **options) -> tuple[App, Probe]:
        probe = Probe()
        conf = {**settings, "scribe.model": "", "rag.enabled": False, "sandbox.enabled": False, "guard.enabled": False,
                "eval.enabled": False, "cache.enabled": True, **options}
        app = App(conf, SYSTEM_PROMPT, User.anonymous(), probe, Recorder(str(traces), conf))
        answers = iter(replies)
        app.sent = []

        def chat(messages, *args, **kwargs):
            app.sent.append(messages)
            return next(answers)
        app.model.chat = chat
        return app, probe
    make.traces = traces
    return make

def test_the_app_answers_from_the_cache_without_the_model(louis):
    app, probe = louis([Reply(content=ANSWER)])
    app._App__answer(QUESTION)
    app.new_session()
    probe.events.clear()
    app._App__answer(PARAPHRASE)
    assert len(app.sent) == 1
    assert probe.told(MODEL_CALL) == []
    names = [event.name for event in probe.events if event.name in (CHAT_TURN_STARTED, CACHE_LOOKUP, CACHE_HIT, CHAT_TEXT,
                                                                     CHAT_REPLY, CHAT_TURN_ENDED)]
    assert names == [CHAT_TURN_STARTED, CACHE_LOOKUP, CACHE_HIT, CHAT_TEXT, CHAT_REPLY, CHAT_TURN_ENDED]
    assert probe.told(CHAT_TEXT)[0].data["text"] == ANSWER
    assert probe.told(CHAT_TURN_ENDED)[0].data["reason"] == "done"
    # Kept in the session as any reply: the conversation goes on from it
    assert [(m.role, m.content) for m in app.session.messages[1:]] == [("user", PARAPHRASE), ("assistant", ANSWER)]

def test_the_reasoning_loop_answers_from_the_cache_too(louis):
    app, probe = louis([Reply(content=ANSWER)], **{"reason.verify": False})
    app.reason(QUESTION)
    app.new_session()
    app.reason(PARAPHRASE)
    assert len(app.sent) == 1 and len(probe.told(CACHE_HIT)) == 1

def test_a_follow_up_in_the_same_session_is_asked_to_the_model(louis):
    app, probe = louis([Reply(content=ANSWER), Reply(content="Encore.")])
    app._App__answer(QUESTION)
    app._App__answer(PARAPHRASE)
    assert len(app.sent) == 2 and probe.told(CACHE_HIT) == []

def test_the_turn_answered_from_the_cache_is_recorded_as_cached(louis):
    app, _ = louis([Reply(content=ANSWER)])
    app._App__answer(QUESTION)
    app.new_session()
    app._App__answer(PARAPHRASE)
    records = [json.loads(line) for line in louis.traces.read_text().splitlines()]
    turns = [record for record in records if record["type"] == "turn"]
    assert [turn["cached"] for turn in turns] == [False, True]
    assert [record["hit"] for record in records if record["type"] == "cache"] == [False, True]

def test_a_cache_that_fails_never_fails_the_turn(louis, monkeypatch):
    app, probe = louis([Reply(content=ANSWER)])
    monkeypatch.setattr(SemanticCache, "lookup", lambda self, *args, **kwargs: 1 / 0)
    app._App__answer(QUESTION)
    assert probe.told(CHAT_TURN_ENDED)[-1].data["reason"] == "done" and len(app.sent) == 1

def test_the_command_switches_shows_and_forgets(louis):
    app, probe = louis([Reply(content=ANSWER)], **{"cache.enabled": False})
    app._App__commands.fetch("/cache on", app)
    assert app.cache.enabled
    app._App__answer(QUESTION)
    app.new_session()
    app._App__answer(PARAPHRASE)
    app._App__commands.fetch("/cache", app)
    assert probe.told(CACHE_STATS)[-1].data["served"] == 1
    app._App__commands.fetch("/cache forget", app)
    assert probe.told(CACHE_CLEARED)[-1].data == {"scope": "last", "entries": 1}
    app._App__commands.fetch("/cache off", app)
    assert not app.cache.enabled
