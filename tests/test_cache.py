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
from cache.rules import same_specifics, timely, situated, why_not, standalone, clean, personal
from cache.seeding import load as load_seed, SEED_DIR
from cache.semantic_cache import SemanticCache
from cache.store import Store
from config.prompt import SYSTEM_PROMPT
from config.settings import settings
from events.event import Event
from events.event_bus import EventBus
from guard.verdict import Verdict, PASS, MASKED
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
    """ An embedding model without Ollama: down raises as Ollama stopped would. asked keeps what it read """
    model: str = "fake-embed"

    def __init__(self, down: bool = False):
        self.down: bool = down
        self.asked: list[str] = []

    def query(self, text: str) -> list[float]:
        if self.down:
            raise EmbedError("Ollama ne répond pas")
        self.asked.append(text)
        return meaning(text)

class FakeReranker:
    """ A cross-encoder without fastembed: the pairs in rejected are not the same question, down raises as it missing would """
    model: str = "fake-rerank"

    def __init__(self, rejected: set[tuple[str, str]] = frozenset(), down: bool = False):
        self.rejected = rejected
        self.down: bool = down
        self.read: list[str] = []

    def score(self, query: str, texts: list[str]) -> list[float]:
        if self.down:
            raise RerankError("le reranking a besoin de fastembed")
        self.read.extend(texts)
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

def called(name: str) -> dict:
    """ A reply of the model in the history of a session, that called a tool """
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": {}}}]}

def ask(cache: SemanticCache, question: str, *, model: str = "qwen", prompt: str = "prompt", history: list[dict] = (),
        answer: str | None = ANSWER, tools: list[tuple[str, bool]] = (), reason: str = "done", events=()):
    """ A turn of the app, as the bus tells it: looked up, then answered by the model unless the cache did """
    bus: EventBus = cache.bus
    bus.dispatch(CHAT_TURN_STARTED)
    hit = cache.lookup(question, model=model, prompt=prompt, history=list(history))
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

@pytest.mark.parametrize("question", [
    QUESTION, "Comment annuler le dernier commit git ?", "Comment trouver le premier élément d'une liste ?",
    "Qu'est-ce qu'une closure ?", "How do I read a JSON file in Python?", "C'est quoi yield ?",
])
def test_a_question_that_means_something_alone_stands_alone(question):
    assert standalone(question) and why_not(question) is None

@pytest.mark.parametrize("question", [
    "Et pour la deuxième ?", "Et en JavaScript ?", "Pourquoi ?", "Explique plus", "Montre-moi le deuxième exemple",
    "Peux-tu corriger ça ?", "Corrige-le s'il te plaît", "Ta réponse est fausse, refais", "Ça ne marche pas chez moi",
    "What about the second one?", "Can you explain it again?", "Mais comment le tester proprement ?",
])
def test_a_question_that_leans_on_what_came_before_is_a_follow_up(question):
    assert not standalone(question) and why_not(question) == "followup"

def test_a_session_is_clean_until_the_model_reads_the_project():
    tools = frozenset({"search_knowledge"})
    assert clean([{"role": "user", "content": "?"}], tools)
    assert clean([called("search_knowledge")], tools)
    assert not clean([called("search_knowledge"), called("cat_file")], tools)

def test_an_answer_that_names_its_user_is_personal():
    assert personal("Bonjour Ada, voici comment faire.", "Ada")
    assert not personal("Avec la bibliothèque Adafruit.", "Ada")
    assert not personal("Bonjour Ada.", None)

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

@pytest.mark.parametrize("question, reason", [
    ("Et pour la deuxième ?", "followup"), ("Quel jour sommes-nous ?", "timely"), ("Que fait ce fichier ?", "project"),
])
def test_a_question_the_cache_may_not_answer_is_not_looked_up_nor_stored(cache, question, reason):
    found = cache()
    ask(found, question)
    assert [(lookup["hit"], lookup["score"], lookup["reason"]) for lookup in told(found, CACHE_LOOKUP)] == \
        [(False, None, reason)]
    assert told(found, CACHE_STORED) == []

def test_a_question_anywhere_in_a_clean_session_is_stored_and_served(cache):
    found = cache()
    earlier = [{"role": "user", "content": "Qu'est-ce qu'une closure ?"}, {"role": "assistant", "content": "..."}]
    ask(found, QUESTION, history=earlier)
    assert len(told(found, CACHE_STORED)) == 1
    assert ask(found, PARAPHRASE, history=earlier * 3) is not None

def test_once_the_model_read_the_project_answers_are_served_but_never_stored(cache):
    found = cache()
    ask(found, QUESTION)
    read = [called("cat_file"), {"role": "tool", "content": "def main(): ...", "tool_name": "cat_file"}]
    assert ask(found, PARAPHRASE, history=read) is not None
    ask(found, "Qu'est-ce qu'une closure ?", history=read)
    assert len(told(found, CACHE_STORED)) == 1

def test_an_answer_that_names_its_user_is_never_stored(cache):
    found = cache(user_name="Ada")
    ask(found, QUESTION, answer="Bonjour Ada ! Avec json.load(f).")
    assert told(found, CACHE_STORED) == []

def test_the_users_share_their_answers_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("LOUIS_CACHE", str(tmp_path / "cache.db"))
    conf = {**settings, "cache.enabled": True, "cache.seed": False}
    ada = SemanticCache.from_settings(conf, EventBus(), User("Ada", 1))
    bob = SemanticCache.from_settings(conf, EventBus(), User("Bob", 2))
    assert ada.stats()["shared"] and bob.stats()["shared"]
    alone = SemanticCache.from_settings({**conf, "cache.shared": False}, EventBus(), User("Ada", 1))
    assert not alone.stats()["shared"]

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

def test_the_same_question_written_the_same_way_needs_no_reranker(cache, monkeypatch):
    monkeypatch.setitem(VECTORS, "comment LIRE un fichier json en python", BASE + 0.01 * noise("case"))
    found = cache(reranker=FakeReranker(down=True))
    ask(found, QUESTION)
    hit = ask(found, "comment LIRE un fichier json en python")
    assert hit is not None and hit.verified == 1.0

def test_an_answer_of_the_model_is_checked_by_its_question(cache):
    reranker = FakeReranker()
    found = cache(reranker=reranker)
    ask(found, QUESTION)
    ask(found, PARAPHRASE)
    assert reranker.read == [QUESTION]

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

# --- The seed ------------------------------------------------------------------------------------------------------

SEED_QUESTION = "Comment indexer un dossier ?"

def write_seed(folder, answer: str = "Avec /index <dossier>.") -> str:
    folder.mkdir(exist_ok=True)
    (folder / "louis.jsonl").write_text(
        json.dumps({"questions": [SEED_QUESTION, "Comment ajouter de la documentation ?"], "answer": answer}) + "\n"
        + "pas du json\n" + json.dumps({"questions": ["Sans réponse ?"]}) + "\n", encoding="utf-8"
    )
    return str(folder)

def test_the_seed_files_of_louis_are_read_whole():
    version, pairs = load_seed(SEED_DIR)
    assert len(pairs) >= 40 and all(question and answer for question, answer in pairs)
    assert version == load_seed(SEED_DIR)[0]

def test_a_seed_line_that_can_not_be_read_is_left_out(tmp_path):
    _, pairs = load_seed(write_seed(tmp_path / "seed"))
    assert [question for question, _ in pairs] == [SEED_QUESTION, "Comment ajouter de la documentation ?"]

def test_the_seed_answers_from_the_first_question_for_any_model_and_user(cache, tmp_path):
    found = cache(seed=write_seed(tmp_path / "seed"), user_id=7)
    hit = ask(found, SEED_QUESTION, model="llama", prompt="another prompt")
    assert hit is not None and hit.seed and hit.answer == "Avec /index <dossier>."
    assert found.stats()["seeds"] == 2 and found.stats()["entries"] == 0

def test_an_answer_of_the_seed_is_checked_by_the_answer_with_its_own_score(cache, tmp_path, monkeypatch):
    monkeypatch.setitem(VECTORS, "Comment je fais pour indexer un dossier ?",
                        np.asarray(meaning(SEED_QUESTION)) + 0.05 * noise("x"))
    answer = "Avec /index <dossier>."
    reranker = FakeReranker()
    found = cache(seed=write_seed(tmp_path / "seed", answer), reranker=reranker, seed_min_score=0.95)
    assert ask(found, "Comment je fais pour indexer un dossier ?", answer=None) is None
    assert reranker.read == [answer]
    assert ask(cache(seed=str(tmp_path / "seed")), "Comment je fais pour indexer un dossier ?").seed

def test_the_warm_up_embeds_the_seed_and_loads_the_reranker_before_the_first_question(cache, tmp_path):
    embedder, reranker = FakeEmbedder(), FakeReranker()
    found = cache(embedder, seed=write_seed(tmp_path / "seed"), reranker=reranker)
    found.warm()
    assert ask(found, SEED_QUESTION) is not None
    # The seed embedded once, by the warm-up: the first lookup only embeds its own question
    assert sorted(embedder.asked) == sorted([SEED_QUESTION, "Comment ajouter de la documentation ?", SEED_QUESTION])
    assert "Louis" in reranker.read

def test_the_warm_up_does_not_embed_a_seed_already_stored(cache, tmp_path):
    folder = write_seed(tmp_path / "seed")
    ask(cache(seed=folder), QUESTION)
    embedder = FakeEmbedder()
    found = cache(embedder, seed=folder)
    found.warm()
    ask(found, SEED_QUESTION)
    assert sorted(embedder.asked) == sorted(["Louis", SEED_QUESTION])

def test_a_warm_up_that_fails_is_done_by_the_first_lookup(cache, tmp_path):
    embedder = FakeEmbedder(down=True)
    found = cache(embedder, seed=write_seed(tmp_path / "seed"))
    found.warm()
    embedder.down = False
    assert ask(found, SEED_QUESTION) is not None

def test_an_answer_discarded_is_never_stored(cache):
    found = cache()
    found.bus.dispatch(CHAT_TURN_STARTED)
    found.lookup(QUESTION, model="qwen", prompt="prompt", history=[])
    found.discard()
    found.bus.dispatch(CHAT_REPLY, content=ANSWER, tools=[])
    found.bus.dispatch(CHAT_TURN_ENDED, reason="done", message=None)
    assert told(found, CACHE_STORED) == []

def test_the_seed_never_expires_nor_is_cleared(cache, tmp_path):
    found = cache(seed=write_seed(tmp_path / "seed"), ttl=10, most=0)
    ask(found, QUESTION)
    found.clock.now += 3600
    found.clear()
    assert ask(found, SEED_QUESTION) is not None and found.stats()["seeds"] == 2

def test_the_seed_is_stored_again_when_its_files_change(cache, tmp_path):
    folder = tmp_path / "seed"
    ask(cache(seed=write_seed(folder)), QUESTION)
    write_seed(folder, answer="Avec /index <dossier> [nom].")
    assert ask(cache(seed=str(folder)), SEED_QUESTION).answer == "Avec /index <dossier> [nom]."
    assert cache(seed=str(folder)).stats()["seeds"] == 2

def test_the_seed_turned_off_is_removed(cache, tmp_path):
    ask(cache(seed=write_seed(tmp_path / "seed")), QUESTION)
    found = cache(seed=None)
    assert ask(found, SEED_QUESTION) is None and found.stats()["seeds"] == 0

def test_the_seed_waits_for_the_embedding_model(cache, tmp_path):
    embedder = FakeEmbedder()
    found = cache(embedder, seed=write_seed(tmp_path / "seed"))
    real = embedder.query
    embedder.query = lambda text: real(text) if text == QUESTION else (_ for _ in ()).throw(EmbedError("down"))
    ask(found, QUESTION)
    assert found.stats()["seeds"] == 0
    embedder.query = real
    assert ask(found, SEED_QUESTION) is not None

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
                "eval.enabled": False, "cache.enabled": True, "cache.seed": False, **options}
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

def test_a_question_later_in_the_same_session_is_answered_from_the_cache(louis):
    app, probe = louis([Reply(content=ANSWER)])
    app._App__answer(QUESTION)
    app._App__answer(PARAPHRASE)
    assert len(app.sent) == 1 and len(probe.told(CACHE_HIT)) == 1

def test_a_follow_up_is_asked_to_the_model(louis):
    app, probe = louis([Reply(content=ANSWER), Reply(content="En JavaScript, JSON.parse.")])
    app._App__answer(QUESTION)
    app._App__answer("Et en JavaScript ?")
    assert len(app.sent) == 2 and probe.told(CACHE_HIT) == []

def test_the_seed_answers_a_new_user_without_the_model(louis):
    app, probe = louis([], **{"cache.seed": True})
    app._App__answer("Comment indexer un dossier ?")
    assert app.sent == []
    assert probe.told(CACHE_HIT)[0].data["seed"] is True
    assert "/index" in probe.told(CHAT_TEXT)[0].data["text"]

class FakeGuard:
    """ The guard without NeMo: keeps the messages its input rails read, masks the emails """
    def __init__(self):
        self.inputs: list[str] = []

    @staticmethod
    def mask(text: str) -> str:
        return text.replace("ada@example.com", "<EMAIL_ADDRESS>")

    def check_input(self, text: str) -> Verdict:
        self.inputs.append(text)
        masked = self.mask(text)
        return Verdict(MASKED if masked != text else PASS, masked)

    def check_output(self, question: str, answer: str) -> Verdict:
        return Verdict(PASS, answer)

    def hide(self, arguments: dict) -> dict:
        return arguments

def test_an_answer_of_the_cache_does_not_wait_for_the_input_rails(louis):
    app, probe = louis([Reply(content=ANSWER)])
    guard = app._App__guard = FakeGuard()
    app._App__answer(QUESTION)
    app._App__answer(PARAPHRASE)
    assert guard.inputs == [QUESTION] and len(app.sent) == 1 and len(probe.told(CACHE_HIT)) == 1

def test_a_message_answered_by_the_cache_is_kept_masked(louis, monkeypatch):
    asked = "Comment on lit un fichier JSON avec Python ? Écris-moi à ada@example.com"
    monkeypatch.setitem(VECTORS, asked, VECTORS[PARAPHRASE])
    app, _ = louis([Reply(content=ANSWER)])
    app._App__guard = FakeGuard()
    app._App__answer(QUESTION)
    app._App__answer(asked)
    assert app.session.messages[-2].content == FakeGuard.mask(asked)

def test_a_message_the_rails_masked_is_never_stored(louis):
    app, probe = louis([Reply(content=ANSWER)])
    app._App__guard = FakeGuard()
    app._App__answer("Comment lire un fichier JSON en Python ? Je suis ada@example.com")
    assert probe.told(CACHE_STORED) == [] and app.cache.stats()["entries"] == 0

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
