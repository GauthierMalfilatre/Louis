##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## SemanticCache class: the answers given before, given again to a question that means the same, without the model
##
## Usage:  cache = SemanticCache.from_settings(settings, bus, user, guard=True)
##         hit = cache.lookup(question, model=..., prompt=..., history=...)   before the model (CACHE_LOOKUP tells how)
##         ...the turn goes on: the cache listens to the bus, and stores its answer once done if it is safe to give again
##
## The answers are shared by the users (cache.shared): a question asked by one is answered at once for the others. And
## the seed (cache/seed/, cache/seeding.py), answers written by the team, makes it useful from the first question on a
## new install: stored on the first lookup, and again each time its files change
##
## A lookup goes in three steps. The embeddings find the questions close in meaning (cache.threshold). The embeddings
## alone can not tell apart the questions that only differ by a word: "lire un fichier JSON" and "écrire un fichier
## JSON" are 0.975 apart with nomic-embed-text, more than most questions asked in other words (python -m cache.evaluate,
## docs/CACHE.md). So the cross-encoder of the reranker reads each one with the new question (~20 ms), and gives its
## answer at once when it finds they ask the same (cache.rerank.min_score). It was trained to tell whether a passage
## answers a question, not whether two questions are the same: it reads an answer of the model against the question it
## was given for (an answer about reading JSON also "answers" a question about writing it: 0.977), but an answer of the
## seed against the new question (cache.seed.min_score), those tell all of what Louis does about something. It never
## confirmed a wrong one, but misses most questions asked otherwise. The closest ones it did not confirm are then asked
## to a small model (cache/matcher.py, ~2.4 s on the CPU): the last word. Without either, nothing is given but the same
## question written the same way: the answers are still stored, for when they are there
##
## The app looks a message up as it was typed, before the input rails of the guard and the model, wherever it comes in
## the session as long as it stands alone (cache/rules.py): on a hit, it gives the answer as a reply (CACHE_HIT), a
## reply the output rails checked when it was kept. On a miss the guard reads the message (masked by it: never stored,
## discard), then the model answers. On a miss in a clean
## session (the model read nothing of the project in it yet), the vector of the question is kept for the end of the
## turn: its answer is stored with it when the turn is done, used no tool but those of cache.tools, none of them failed,
## the guard did not refuse the reply, the reasoning loop gave no answer it found wrong, and it does not name the user.
## What is stored is what the user read: the question as the guard let it through (masked), the reply as it was shown
##
from cache.rules import why_not, same_specifics, same_text, clean, personal
from cache.matcher import Matcher, MatchError
from cache.seeding import SEED_DIR, load as load_seed
from cache.store import Store, Scope, Entry, normalized, SEED
from rag.embedder import Embedder, EmbedError
from rag.reranker import Reranker, RerankError
from events.event import Event
from events.event_bus import EventBus
from events.event_list import CHAT_TURN_STARTED, CHAT_TURN_ENDED, CHAT_REPLY, TOOL_CALL_ENDED, GUARD_TRIGGERED
from events.event_list import REASONING_CHECK, RAG_INDEXED, RAG_FORGOTTEN
from events.event_list import CACHE_LOOKUP, CACHE_STORED, CACHE_CLEARED
from monitor.recorder import prompt_version
from session.user import User
from config.settings import settings as default_settings
from logger.logger import log
from collections.abc import Callable
from dataclasses import dataclass, field
import numpy as np
import os
import threading
import time

# The tools whose sources are the knowledge base: the answers that used them are forgotten when it changes
RAG_TOOLS: tuple[str, ...] = ("search_knowledge",)
# Entries compared with each question beyond the closest: the closest may differ by a number, the next one not
CANDIDATES: int = 5
# Of those the reranker did not confirm, the closest ones asked to the matcher: ~2.4 s each, paid by the misses too
MATCHED: int = 2

def cache_path() -> str:
    """ Where the cache is: LOUIS_CACHE, or the file of the settings in the working directory (as louis.db) """
    return os.environ.get("LOUIS_CACHE") or os.path.join(os.getcwd(), default_settings["cache.file"])

@dataclass(frozen=True, slots=True)
class Hit:
    """
        An answer given before, to give again: score is how close the questions are in meaning (0 to 1), verified how
        sure the reranker is they ask the same (0 to 1, None without it), age its seconds, seed whether the team wrote
        it, by what found them the same: "text" (written the same), "reranker", "matcher" or "meaning" (verify off)
    """
    id      : int
    question: str
    answer  : str
    score   : float
    verified: float | None
    age     : float
    hits    : int
    seed    : bool = False
    by      : str  = "reranker"

@dataclass
class Pending:
    """ A question the cache had no answer for: stored with its answer, if the turn gives one safe to give again """
    scope   : Scope
    question: str
    vector  : np.ndarray

@dataclass
class Turn:
    """ What the turn being answered did so far """
    tools  : set[str] = field(default_factory=set)
    failed : bool     = False
    refused: bool     = False
    left   : bool     = False
    answer : str      = ""

class SemanticCache:
    """ Looked up by the app before the model, fed by the bus once a turn is done """
    def __init__(self, bus: EventBus, store: Store, embedder: Embedder | None, *, enabled: bool = True,
                 threshold: float = 0.78, reranker: Reranker | None = None, matcher: Matcher | None = None,
                 verify: bool = True,
                 min_score: float = 0.35, seed_min_score: float = 0.75, ttl: float = 7 * 24 * 3600, most: int = 1000,
                 tools: list[str] | None = None, user_id: int | None = None, user_name: str | None = None,
                 guard: bool = False, seed: str | None = None, clock: Callable[[], float] = time.time):
        """
            Init the cache on the bus of the app. With verify, a question close enough in meaning (threshold) must also be
            the same for the reranker (min_score; seed_min_score for its answer, against an answer of the seed), or for
            the matcher: without either, nothing is given but the same question written the same way. Without verify,
            the meaning is enough
            (questions that differ by one word get each other's answer). user_id is None for a cache the users share;
            user_name: an answer that names them is never stored (None: the anonymous user). guard: the guard checks the
            replies, an answer stored without it is never given while it does. seed: the folder of the seed files (None:
            no seed). clock gives the time (the tests)
        """
        self.__bus      : EventBus        = bus
        self.__store    : Store           = store
        self.__embedder : Embedder | None = embedder
        self.__enabled  : bool            = enabled
        self.__threshold: float           = threshold
        self.__reranker : Reranker | None = reranker
        self.__matcher  : Matcher | None  = matcher
        self.__verify   : bool            = verify
        self.__min_score: float           = min_score
        self.__seed_min : float           = seed_min_score
        self.__ttl     : float           = ttl
        self.__most     : int             = most
        self.__tools    : frozenset[str]  = frozenset(tools if tools is not None else RAG_TOOLS)
        self.__user_id  : int | None      = user_id
        self.__user_name: str | None      = user_name
        self.__guard    : bool            = guard
        self.__seed     : str | None      = seed
        # The seed is stored once per run at most, on the first lookup the embedding model answers
        self.__seeded   : bool            = False
        # warm(): the threads that load the models while the user types, and the seed they embedded (version, entries)
        self.__warming  : list[threading.Thread] = []
        self.__prepared : tuple[str, list[tuple[str, str, np.ndarray]]] | None = None
        self.__clock    : Callable[[], float] = clock
        self.__pending  : Pending | None  = None
        self.__turn     : Turn | None     = None
        # The entry served last, for /cache forget
        self.__served   : int | None      = None
        # This run: the questions looked up, and the ones answered from the cache
        self.__lookups  : int             = 0
        self.__hits     : int             = 0
        # The embedding model or the reranker failed: said once in the log, not at every message
        self.__warned   : bool            = False
        self.__unverified: bool           = False
        self.__unmatched: bool            = False

        bus.subscribe(self.__on_turn_started, CHAT_TURN_STARTED)
        bus.subscribe(self.__on_tool_ended, TOOL_CALL_ENDED)
        bus.subscribe(self.__on_guard, GUARD_TRIGGERED)
        bus.subscribe(self.__on_check, REASONING_CHECK)
        bus.subscribe(self.__on_reply, CHAT_REPLY)
        bus.subscribe(self.__on_turn_ended, CHAT_TURN_ENDED)
        bus.subscribe(self.__on_knowledge, RAG_INDEXED, RAG_FORGOTTEN)

    @classmethod
    def from_settings(cls, settings: dict, bus: EventBus, user: User, guard: bool = False,
                      reranker: Reranker | None = None) -> "SemanticCache":
        """
            The cache the settings describe for the user, with the embedding model of the knowledge base on the CPU, and
            its reranker when it is given one (the same model is loaded once), else one of its own
        """
        model: str | None = settings.get("rag.embed.model")
        embedder: Embedder | None = Embedder(
            settings["chat.uri"], model, settings.get("rag.embed.query_prefix", ""),
            settings.get("rag.embed.document_prefix", ""), gpu=False
        ) if model else None
        verify: bool = bool(settings.get("cache.rerank.enabled", True))
        if verify and (reranker is None or reranker.model != settings.get("rag.rerank.model")):
            reranker = Reranker(settings.get("rag.rerank.model", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"),
                                max_chars=settings.get("rag.rerank.max_chars", 0))
        judge: str | None = settings.get("cache.match.model")
        matcher: Matcher | None = Matcher(
            settings["chat.uri"], judge, settings.get("cache.match.gpu", False), settings.get("scribe.keepalive", "30m")
        ) if verify and judge else None
        return cls(
            bus, Store(cache_path()), embedder,
            enabled=bool(settings.get("cache.enabled", True)),
            threshold=float(settings.get("cache.threshold", 0.78)),
            reranker=reranker if verify else None,
            matcher=matcher,
            verify=verify,
            min_score=float(settings.get("cache.rerank.min_score", 0.35)),
            seed_min_score=float(settings.get("cache.seed.min_score", 0.75)),
            ttl=float(settings.get("cache.ttl", 7 * 24 * 3600)),
            most=int(settings.get("cache.max_entries", 1000)),
            tools=list(settings.get("cache.tools", RAG_TOOLS)),
            user_id=None if settings.get("cache.shared", True) else user.id,
            user_name=None if user.is_anonymous else user.name,
            guard=guard,
            seed=SEED_DIR if settings.get("cache.seed", True) else None
        )

    @property
    def enabled(self) -> bool:
        """ Whether the questions are looked up and the answers stored """
        return self.__enabled

    @enabled.setter
    def enabled(self, state: bool) -> None:
        """ Look the next questions up, or not """
        self.__enabled = state
        self.__pending = None
        if state:
            self.warm()

    def warm(self) -> None:
        """
            Get ready while the user types: the embedding model and the reranker loaded, the questions of the seed
            embedded if they changed, each in a thread of its own. The first lookup waits for them, then stores the seed.
            Measured on a new install: 6.8s for the seed, 5.8s for the reranker, that the first question no longer waits
        """
        if self.__warming or self.__embedder is None:
            return
        jobs: list[Callable[[], None]] = [self.__prepare_seed]
        if self.__verify and self.__reranker is not None:
            jobs.append(lambda: self.__reranker.score("Louis", ["Louis"]))
        if self.__matcher is not None:
            jobs.append(lambda: self.__matcher.same("Louis", "Louis"))
        for job in jobs:
            thread = threading.Thread(target=self.__quietly, args=(job,), daemon=True, name="louis-cache-warm")
            self.__warming.append(thread)
            thread.start()

    def discard(self) -> None:
        """ Never store the answer of the question looked up last (the guard masked it: it holds sensitive data) """
        self.__pending = None

    def __quietly(self, job: Callable[[], None]) -> None:
        """ Run a job of the warm-up: one that fails is done by the first lookup, as without the warm-up """
        try:
            job()
        except (EmbedError, RerankError, MatchError) as e:
            log.info(f"[cache] warm-up left to the first lookup: {e.message}")
        except Exception:
            log.exception("[cache] the warm-up failed")

    def __prepare_seed(self) -> None:
        """ Embed the questions of the seed if they changed, else one word: the embedding model is loaded either way """
        version, pairs = load_seed(self.__seed)
        stored: str | None = self.__store.peek_seed_version(self.__embedder.model)
        if stored != version and (pairs or stored is not None):
            self.__prepared = (version, [(question, answer, normalized(self.__embedder.query(question)))
                                         for question, answer in pairs])
        else:
            self.__embedder.query("Louis")

    @property
    def path(self) -> str:
        """ Get the file of the cache """
        return self.__store.path

    def lookup(self, question: str, *, model: str, prompt: str, history: list[dict]) -> Hit | None:
        """
            The answer given before (or by the seed) to a question that means the same, None if there is none. prompt is
            the system prompt of the session (without its context), history the session in the format of the model API.
            A miss in a clean session keeps the vector of the question: the answer of the turn is stored with it. Told
            by CACHE_LOOKUP
        """
        self.__pending = None
        if not self.__enabled:
            return None
        start: float = time.perf_counter()
        reason: str | None = why_not(question)
        if reason is None and self.__embedder is None:
            reason = "embed"
        vector: np.ndarray | None = None
        if reason is None:
            try:
                vector = normalized(self.__embedder.query(question))
            except EmbedError as e:
                if not self.__warned:
                    log.warning(f"[cache] not looked up: {e.message}")
                    self.__warned = True
            if vector is None:
                reason = "embed"
        if reason is not None:
            self.__bus.dispatch(CACHE_LOOKUP, hit=False, score=None, duration=round(time.perf_counter() - start, 3),
                                reason=reason, matched=0)
            return None

        scope: Scope = Scope(self.__user_id, model, prompt_version(prompt), self.__embedder.model)
        now: float = self.__clock()
        self.__plant(now)
        candidates: list[tuple[Entry, float]] = self.__store.nearest(scope, vector, now - self.__ttl, CANDIDATES)
        best: float | None = round(candidates[0][1], 4) if candidates else None
        close: list[tuple[Entry, float]] = []
        for entry, score in candidates:
            if score < self.__threshold:
                break
            if self.__guard and not entry.guard:
                continue
            if not same_specifics(question, entry.question):
                log.info(f"[cache] {score:.3f} close to #{entry.id}, but not about the same details: {entry.question!r}")
                continue
            close.append((entry, score))
        found: Hit | None = None
        verified: list[float | None] = self.__verified(question, [entry for entry, _ in close])
        unsure: list[tuple[Entry, float, float]] = []
        for (entry, score), checked in zip(close, verified):
            if checked is None or checked >= (self.__seed_min if entry.origin == SEED else self.__min_score):
                by: str = "meaning" if checked is None else "text" if same_text(question, entry.question) else "reranker"
                found = self.__hit(entry, score, checked, now, by)
                break
            log.info(f"[cache] {score:.3f} close to #{entry.id}, but not "
                     f"{'its answer' if entry.origin == SEED else 'the same question'} for the reranker "
                     f"({checked:.3f}): {entry.question!r}")
            unsure.append((entry, score, checked))
        judged: int = 0
        if found is None and self.__matcher is not None:
            for entry, score, checked in unsure[:MATCHED]:
                judged += 1
                if self.__matched(question, entry):
                    found = self.__hit(entry, score, checked, now, "matcher")
                    break
                log.info(f"[cache] {score:.3f} close to #{entry.id}, but not the same question for "
                         f"{self.__matcher.model}: {entry.question!r}")

        self.__lookups += 1
        if found is None:
            # Once the model read the project in this session, what it says next may lean on it
            if clean(history, self.__tools):
                self.__pending = Pending(scope, question, vector)
        else:
            self.__store.hit(found.id, now)
            self.__served = found.id
            self.__hits += 1
            log.info(f"[cache] hit #{found.id} ({found.score:.3f}, by {found.by}, verified {found.verified}): "
                     f"{found.question!r}")
        self.__bus.dispatch(CACHE_LOOKUP, hit=found is not None, score=found.score if found else best,
                            duration=round(time.perf_counter() - start, 3), reason=None, matched=judged)
        return found

    @staticmethod
    def __hit(entry: Entry, score: float, verified: float | None, now: float, by: str) -> Hit:
        return Hit(entry.id, entry.question, entry.answer, round(score, 4),
                   round(verified, 4) if verified is not None else None, now - entry.created_at, entry.hits + 1,
                   entry.origin == SEED, by)

    def __matched(self, question: str, entry: Entry) -> bool:
        """ Whether the matcher finds the question the same as the one of the entry. One that fails finds nothing """
        try:
            return self.__matcher.same(entry.question, question)
        except MatchError as e:
            if not self.__unmatched:
                log.warning(f"[cache] the questions are not compared by {self.__matcher.model}: {e.message}")
                self.__unmatched = True
            return False

    def __plant(self, now: float) -> None:
        """
            Store the questions of the seed files, embedded by the model of the cache, if they changed since they were
            (or the seed was turned off: the old ones are removed). Once per run: a few seconds the first time (~30 ms a
            question), nothing after. The embedding model failing, it is tried again on the next lookup
        """
        if self.__seeded:
            return
        for thread in self.__warming:
            thread.join()
        version, pairs = load_seed(self.__seed)
        stored: str | None = self.__store.seed_version(self.__embedder.model)
        # No seed, and none stored before: nothing to remove, the file is not created for it
        if stored != version and (pairs or stored is not None):
            prepared, self.__prepared = self.__prepared, None
            try:
                entries = prepared[1] if prepared is not None and prepared[0] == version else \
                    [(question, answer, normalized(self.__embedder.query(question))) for question, answer in pairs]
            except EmbedError as e:
                log.warning(f"[cache] the seed is not stored yet: {e.message}")
                return
            count: int = self.__store.replace_seed(
                self.__embedder.model, version, [entry for entry in entries if entry[2] is not None], now
            )
            log.info(f"[cache] seed {version}: {count} questions stored")
        self.__seeded = True

    def __verified(self, question: str, entries: list[Entry]) -> list[float | None]:
        """
            How sure the reranker is that each entry is the answer to the question (0 to 1), in the same order: its
            question read against the question, or its answer for the seed. Without verify, None for each: the meaning
            was enough. The same question written the same way is 1 without asking it. Without a reranker that answers,
            0 for the others: they are not given
        """
        if not self.__verify:
            return [None] * len(entries)
        scores: list[float] = [1.0 if same_text(question, entry.question) else 0.0 for entry in entries]
        unsure: list[int] = [i for i, score in enumerate(scores) if score < 1.0]
        if unsure and self.__reranker is not None:
            try:
                read: list[float] = self.__reranker.score(
                    question, [entries[i].answer if entries[i].origin == SEED else entries[i].question for i in unsure]
                )
                for i, score in zip(unsure, read):
                    scores[i] = score
            except RerankError as e:
                if not self.__unverified:
                    log.warning(f"[cache] only the same questions are given, the others can not be checked: {e.message}")
                    self.__unverified = True
        return scores

    def stats(self) -> dict:
        """ What /cache shows: as CACHE_STATS tells it """
        entries, hits, seeds = self.__store.count(self.__user_id)
        return {
            "enabled"  : self.__enabled,
            "entries"  : entries,
            "seeds"    : seeds,
            "shared"   : self.__user_id is None,
            "hits"     : hits,
            "lookups"  : self.__lookups,
            "served"   : self.__hits,
            "hit_rate" : self.__hits / self.__lookups if self.__lookups else None,
            "threshold": self.__threshold,
            "file"     : self.__store.path,
        }

    def forget_last(self) -> int:
        """ Remove the answer served last (it was wrong): 1 if there was one, told by CACHE_CLEARED """
        if self.__served is None:
            return 0
        removed: int = self.__store.remove(self.__served)
        self.__served = None
        self.__bus.dispatch(CACHE_CLEARED, scope="last", entries=removed)
        return removed

    def clear(self) -> int:
        """
            Remove every answer of the model to the user (to all of them when shared), never the seed: how many, told by
            CACHE_CLEARED
        """
        removed: int = self.__store.clear(self.__user_id)
        self.__served = None
        self.__bus.dispatch(CACHE_CLEARED, scope="all", entries=removed)
        return removed

    def __on_turn_started(self, event: Event) -> None:
        """ A message of the user: looked up next (or not, a /json), what comes until its end belongs to it """
        self.__pending = None
        self.__turn = Turn()

    def __on_tool_ended(self, event: Event) -> None:
        if self.__turn is not None:
            self.__turn.tools.add(event.data["name"])
            self.__turn.failed |= not event.data["ok"]

    def __on_guard(self, event: Event) -> None:
        """ A reply the guard refused is its refusal: no answer to give again """
        if self.__turn is not None and event.data["stage"] == "output" and event.data["action"] == "refused":
            self.__turn.refused = True

    def __on_check(self, event: Event) -> None:
        """ The reasoning loop gave its answer with problems it found in it: never given again """
        if self.__turn is not None and not event.data["ok"] and not event.data["revise"]:
            self.__turn.left = True

    def __on_reply(self, event: Event) -> None:
        """ The answer is the last reply that called no tool """
        if self.__turn is not None and not event.data["tools"] and event.data["content"].strip():
            self.__turn.answer = event.data["content"]

    def __on_turn_ended(self, event: Event) -> None:
        """ A turn done: its answer stored with the question looked up, if it is safe to give again """
        turn, pending = self.__turn, self.__pending
        self.__turn, self.__pending = None, None
        if turn is None or pending is None or not self.__enabled or event.data["reason"] != "done":
            return
        if turn.refused or turn.failed or turn.left or not turn.answer.strip():
            return
        if not turn.tools <= self.__tools:
            log.info(f"[cache] not stored: the answer used {', '.join(sorted(turn.tools - self.__tools))}")
            return
        if personal(turn.answer, self.__user_name):
            log.info("[cache] not stored: the answer names the user")
            return
        now: float = self.__clock()
        identifier: int = self.__store.add(pending.scope, pending.question, turn.answer, pending.vector,
                                           sorted(turn.tools), self.__guard, now)
        self.__store.expire(now - self.__ttl)
        self.__store.evict(self.__most)
        log.info(f"[cache] stored #{identifier}: {pending.question!r}")
        self.__bus.dispatch(CACHE_STORED, id=identifier, tools=sorted(turn.tools))

    def __on_knowledge(self, event: Event) -> None:
        """ The knowledge base changed: the answers that looked it up may no longer hold """
        if event.name == RAG_INDEXED and not (event.data.get("updated") or event.data.get("removed")):
            return
        removed: int = self.__store.drop_using(list(RAG_TOOLS))
        if removed:
            log.info(f"[cache] the knowledge base changed: {removed} answers forgotten")
            self.__bus.dispatch(CACHE_CLEARED, scope="rag", entries=removed)
