##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## SemanticCache class: the answers given before, given again to a question that means the same, without the model
##
## Usage:  cache = SemanticCache.from_settings(settings, bus, user_id, guard=True)
##         hit = cache.lookup(question, model=..., prompt=..., first=True)   before the model (CACHE_LOOKUP tells how)
##         ...the turn goes on: the cache listens to the bus, and stores its answer once done if it is safe to give again
##
## A lookup goes in two steps, as a search of the knowledge base does. The embeddings find the questions close in
## meaning (cache.threshold), then the cross-encoder of the reranker reads each one with the new question, and only gives
## its answer when it finds they ask the same (cache.rerank.min_score). The embeddings alone can not tell apart the
## questions that only differ by a word: "lire un fichier JSON" and "écrire un fichier JSON" are 0.975 apart with
## nomic-embed-text, more than most questions asked in other words (python -m cache.evaluate, docs/CACHE.md). Without
## the reranker (fastembed missing), nothing is given: the answers are still stored, for when it is there
##
## The app looks a question up once the guard let it through, before the model: on a hit, it gives the answer as a
## reply (CACHE_HIT). On a miss, the vector of the question is kept for the end of the turn: its answer is stored with
## it when the turn is done, used no tool but those of cache.tools, none of them failed, the guard did not refuse the
## reply, and the reasoning loop gave no answer it found wrong. What is stored is what the user read: the question as
## the guard let it through (masked), the reply as it was shown
##
from cache.rules import why_not, same_specifics
from cache.store import Store, Scope, Entry, normalized
from rag.embedder import Embedder, EmbedError
from rag.reranker import Reranker, RerankError
from events.event import Event
from events.event_bus import EventBus
from events.event_list import CHAT_TURN_STARTED, CHAT_TURN_ENDED, CHAT_REPLY, TOOL_CALL_ENDED, GUARD_TRIGGERED
from events.event_list import REASONING_CHECK, RAG_INDEXED, RAG_FORGOTTEN
from events.event_list import CACHE_LOOKUP, CACHE_STORED, CACHE_CLEARED
from monitor.recorder import prompt_version
from config.settings import settings as default_settings
from logger.logger import log
from collections.abc import Callable
from dataclasses import dataclass, field
import numpy as np
import os
import time

# The tools whose sources are the knowledge base: the answers that used them are forgotten when it changes
RAG_TOOLS: tuple[str, ...] = ("search_knowledge",)
# Entries compared with each question beyond the closest: the closest may differ by a number, the next one not
CANDIDATES: int = 5

def cache_path() -> str:
    """ Where the cache is: LOUIS_CACHE, or the file of the settings in the working directory (as louis.db) """
    return os.environ.get("LOUIS_CACHE") or os.path.join(os.getcwd(), default_settings["cache.file"])

@dataclass(frozen=True, slots=True)
class Hit:
    """
        An answer given before, to give again: score is how close the questions are in meaning (0 to 1), verified how
        sure the reranker is they ask the same (0 to 1, None without it), age its seconds
    """
    id      : int
    question: str
    answer  : str
    score   : float
    verified: float | None
    age     : float
    hits    : int

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
                 threshold: float = 0.80, reranker: Reranker | None = None, verify: bool = True,
                 min_score: float = 0.35, ttl: float = 7 * 24 * 3600, most: int = 1000,
                 tools: list[str] | None = None, scope: str = "first", user_id: int | None = None, guard: bool = False,
                 clock: Callable[[], float] = time.time):
        """
            Init the cache on the bus of the app. With verify, a question close enough in meaning (threshold) must also be
            the same for the reranker (min_score): without one, nothing is given. Without verify, the meaning is enough
            (questions that differ by one word get each other's answer). user_id is None for a cache the users share.
            guard: the guard checks the replies, an answer stored without it is never given while it does. clock gives
            the time (the tests)
        """
        self.__bus      : EventBus        = bus
        self.__store    : Store           = store
        self.__embedder : Embedder | None = embedder
        self.__enabled  : bool            = enabled
        self.__threshold: float           = threshold
        self.__reranker : Reranker | None = reranker
        self.__verify   : bool            = verify
        self.__min_score: float           = min_score
        self.__ttl      : float           = ttl
        self.__most     : int             = most
        self.__tools    : frozenset[str]  = frozenset(tools if tools is not None else RAG_TOOLS)
        self.__scope    : str             = scope
        self.__user_id  : int | None      = user_id
        self.__guard    : bool            = guard
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

        bus.subscribe(self.__on_turn_started, CHAT_TURN_STARTED)
        bus.subscribe(self.__on_tool_ended, TOOL_CALL_ENDED)
        bus.subscribe(self.__on_guard, GUARD_TRIGGERED)
        bus.subscribe(self.__on_check, REASONING_CHECK)
        bus.subscribe(self.__on_reply, CHAT_REPLY)
        bus.subscribe(self.__on_turn_ended, CHAT_TURN_ENDED)
        bus.subscribe(self.__on_knowledge, RAG_INDEXED, RAG_FORGOTTEN)

    @classmethod
    def from_settings(cls, settings: dict, bus: EventBus, user_id: int | None, guard: bool = False,
                      reranker: Reranker | None = None) -> "SemanticCache":
        """
            The cache the settings describe, with the embedding model of the knowledge base on the CPU, and its reranker
            when it is given one (the same model is loaded once), else one of its own
        """
        model: str | None = settings.get("rag.embed.model")
        embedder: Embedder | None = Embedder(
            settings["chat.uri"], model, settings.get("rag.embed.query_prefix", ""),
            settings.get("rag.embed.document_prefix", ""), gpu=False
        ) if model else None
        verify: bool = bool(settings.get("cache.rerank.enabled", True))
        if verify and (reranker is None or reranker.model != settings.get("rag.rerank.model")):
            reranker = Reranker(settings.get("rag.rerank.model", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"))
        return cls(
            bus, Store(cache_path()), embedder,
            enabled=bool(settings.get("cache.enabled", False)),
            threshold=float(settings.get("cache.threshold", 0.80)),
            reranker=reranker if verify else None,
            verify=verify,
            min_score=float(settings.get("cache.rerank.min_score", 0.35)),
            ttl=float(settings.get("cache.ttl", 7 * 24 * 3600)),
            most=int(settings.get("cache.max_entries", 1000)),
            tools=list(settings.get("cache.tools", RAG_TOOLS)),
            scope=settings.get("cache.scope", "first"),
            user_id=None if settings.get("cache.shared", False) else user_id,
            guard=guard
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

    @property
    def path(self) -> str:
        """ Get the file of the cache """
        return self.__store.path

    def lookup(self, question: str, *, model: str, prompt: str, first: bool) -> Hit | None:
        """
            The answer given before to a question that means the same, None if there is none. prompt is the system
            prompt of the session (without its context), first whether the user said nothing yet in it. A miss keeps
            the vector of the question: the answer of the turn is stored with it. Told by CACHE_LOOKUP
        """
        self.__pending = None
        if not self.__enabled:
            return None
        start: float = time.perf_counter()
        reason: str | None = why_not(question, first, self.__scope)
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
                                reason=reason)
            return None

        scope: Scope = Scope(self.__user_id, model, prompt_version(prompt), self.__embedder.model)
        now: float = self.__clock()
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
        for (entry, score), verified in zip(close, self.__verified(question, [entry for entry, _ in close])):
            if verified is None or verified >= self.__min_score:
                found = Hit(entry.id, entry.question, entry.answer, round(score, 4),
                            round(verified, 4) if verified is not None else None, now - entry.created_at, entry.hits + 1)
                break
            log.info(f"[cache] {score:.3f} close to #{entry.id}, but not the same question for the reranker "
                     f"({verified:.3f}): {entry.question!r}")

        self.__lookups += 1
        if found is None:
            self.__pending = Pending(scope, question, vector)
        else:
            self.__store.hit(found.id, now)
            self.__served = found.id
            self.__hits += 1
            log.info(f"[cache] hit #{found.id} ({found.score:.3f}, verified {found.verified}): {found.question!r}")
        self.__bus.dispatch(CACHE_LOOKUP, hit=found is not None, score=found.score if found else best,
                            duration=round(time.perf_counter() - start, 3), reason=None)
        return found

    def __verified(self, question: str, entries: list[Entry]) -> list[float | None]:
        """
            How sure the reranker is that each entry asks the same as the question (0 to 1), in the same order. Without
            verify, None for each: the meaning was enough. Without a reranker that answers, 0 for each: nothing is given
        """
        if not entries:
            return []
        if not self.__verify:
            return [None] * len(entries)
        if self.__reranker is not None:
            try:
                return self.__reranker.score(question, [entry.question for entry in entries])
            except RerankError as e:
                if not self.__unverified:
                    log.warning(f"[cache] no answer given, they can not be checked: {e.message}")
                    self.__unverified = True
        return [0.0] * len(entries)

    def stats(self) -> dict:
        """ What /cache shows: as CACHE_STATS tells it """
        entries, hits = self.__store.count(self.__user_id)
        return {
            "enabled"  : self.__enabled,
            "entries"  : entries,
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
        """ Remove every answer of the user: how many, told by CACHE_CLEARED """
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
