##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Collector: the samples the judge reads, made from what goes on the bus during a turn, as the recorder does
##
## A turn gives a sample when it is done: the question (as the model read it), the last reply of the model (the one
## that called no tool: the answer the user read), and the results of the tools of eval.sources that worked. A turn
## that ended otherwise (cancelled, error, refused...) gave no answer to judge, and neither did a reply the guard
## refused (its text is the refusal) nor a structured one (/json: its JSON is checked by its schema). An answer of the
## semantic cache is none either: it was judged when the model gave it
##
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from events.event import Event
from events.event_bus import EventBus
from events.event_list import CHAT_TURN_STARTED, CHAT_TURN_ENDED, CHAT_REPLY, MODEL_CALL, GUARD_TRIGGERED
from events.event_list import TOOL_CALL_STARTED, TOOL_CALL_ENDED, SESSION_CREATED, SESSION_SAVED, SESSION_RESUMED
from events.event_list import CACHE_HIT
from eval.sample import Sample, Source
from monitor.recorder import prompt_version
import uuid

@dataclass
class Turn:
    """ What a turn being answered gave so far """
    question: str | None   = None
    answer  : str          = ""
    model   : str | None   = None
    prompt  : str | None   = None
    sources : list[Source] = field(default_factory=list)
    refused : bool         = False
    cached  : bool         = False

class Collector:
    """ Listens to the bus, and gives each answer of Louis to on_sample once its turn is done """
    def __init__(self, on_sample: Callable[[Sample], None], tools: Iterable[str]):
        """ Init a collector, the results of the tools named are the sources of the answers """
        self.__on_sample: Callable[[Sample], None] = on_sample
        self.__tools    : frozenset[str]           = frozenset(tools)
        self.__turn     : Turn | None              = None
        self.__session  : int | None               = None
        # The arguments of the call running: TOOL_CALL_ENDED does not repeat them
        self.__arguments: dict                     = {}

    def bind(self, bus: EventBus) -> "Collector":
        """ Collect what happens on the bus, from now on """
        bus.subscribe(self.__on_session, SESSION_CREATED, SESSION_SAVED, SESSION_RESUMED)
        bus.subscribe(self.__on_turn_started, CHAT_TURN_STARTED)
        bus.subscribe(self.__on_model_call, MODEL_CALL)
        bus.subscribe(self.__on_tool_started, TOOL_CALL_STARTED)
        bus.subscribe(self.__on_tool_ended, TOOL_CALL_ENDED)
        bus.subscribe(self.__on_guard, GUARD_TRIGGERED)
        bus.subscribe(self.__on_reply, CHAT_REPLY)
        bus.subscribe(self.__on_cache_hit, CACHE_HIT)
        bus.subscribe(self.__on_turn_ended, CHAT_TURN_ENDED)
        return self

    def __on_cache_hit(self, event: Event) -> None:
        """ An answer given again by the cache, without the model: nothing new to judge """
        if self.__turn is not None:
            self.__turn.cached = True

    def __on_session(self, event: Event) -> None:
        """ The session of the next answers: a new one has no id until the user writes in it """
        self.__session = None if event.name == SESSION_CREATED else event.data["id"]

    def __on_turn_started(self, event: Event) -> None:
        """ A message of the user: what comes until the end of its turn belongs to its answer """
        self.__turn = Turn()

    def __on_model_call(self, event: Event) -> None:
        """ The question is the last message of the user the first request is given (a nudge comes later) """
        turn: Turn | None = self.__turn
        if turn is None:
            return
        if turn.question is None:
            turn.question = next((m.get("content") for m in reversed(event.data["messages"]) if m["role"] == "user"), None)
        turn.model, turn.prompt = event.data["model"], prompt_version(event.data["system"])

    def __on_tool_started(self, event: Event) -> None:
        """ Keep the arguments of the call for its end """
        self.__arguments = event.data["arguments"]

    def __on_tool_ended(self, event: Event) -> None:
        """ What a tool of the sources read: one that could not do it read nothing """
        data: dict = event.data
        if self.__turn is not None and data["name"] in self.__tools and data["ok"] and data["result"].strip():
            self.__turn.sources.append(Source(data["name"], dict(self.__arguments), data["result"]))
        self.__arguments = {}

    def __on_guard(self, event: Event) -> None:
        """ A reply the guard refused is replaced by the refusal: nothing of the model to judge """
        if self.__turn is not None and event.data["stage"] == "output" and event.data["action"] == "refused":
            self.__turn.refused = True

    def __on_reply(self, event: Event) -> None:
        """ The answer is the last reply that called no tool: the ones before only said what the model was doing """
        if self.__turn is not None and not event.data["tools"] and event.data["content"].strip():
            self.__turn.answer = event.data["content"]

    def __on_turn_ended(self, event: Event) -> None:
        """ A turn done with an answer gives its sample """
        turn: Turn | None = self.__turn
        self.__turn = None
        if turn is None or event.data["reason"] != "done" or turn.refused or turn.cached or not turn.answer \
                or not turn.question:
            return
        self.__on_sample(Sample(
            id=uuid.uuid4().hex[:12],
            question=turn.question,
            answer=turn.answer,
            sources=turn.sources,
            model=turn.model,
            prompt=turn.prompt,
            session=self.__session
        ))
