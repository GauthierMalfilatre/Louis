##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Recorder: every call to the model and to the tools, one JSON line each, for the metrics (louis --dashboard)
##
## Each record has its version (v), its time (ts, UTC), its type, and the run (one launch of louis) it belongs to:
##   run     louis started: the model, and the settings that change how fast it replies
##   prompt  a system prompt met for the first time in the run, whole: the other records name it by its version
##   llm     one request to the model: what it was given, what it replied, its latency, its tokens, how it went
##   tool    one tool call: its arguments, whether it worked, how long it took
##   guard   a rail of the guard changed a message
##   rag     one look-up in the knowledge base: its query, how it searched, what it found, how long it took
##   turn    one message of the user answered: how it ended, how long the whole answer took, what it cost
##   structured  a reply asked as JSON (/json, --ask): its schema, whether it matched, after how many replies
## The records of a turn share its id. The long texts are cut: the whole conversation is in the database and the log.
## A tool that asks the user waits for the answer: the duration of the call and the latency of the turn count that
## time, waited tells how much of it was the user's (the metrics take it out)
##
from dataclasses import dataclass
from datetime import datetime, timezone
from events.event import Event
from events.event_bus import EventBus
from events.event_list import APP_STARTED, SESSION_CREATED, SESSION_SAVED, SESSION_RESUMED, GUARD_TRIGGERED
from events.event_list import CHAT_TURN_STARTED, CHAT_TURN_ENDED, MODEL_CALL, TOOL_CALL_STARTED, TOOL_CALL_ENDED
from events.event_list import TOOL_BEGFOR_PERMISSION, TOOL_GRANT_PERMISSION, RAG_RETRIEVED, STRUCTURED_REPLY
from config.settings import settings as default_settings
from logger.logger import log, scrub
import hashlib
import json
import os
import time
import uuid

# Bumped when a field changes its meaning: the metrics can tell the old records apart
VERSION: int = 1

# The settings that change the latency or the tokens of a reply: kept with each run, to explain a drift
RUN_SETTINGS: tuple[str, ...] = (
    "chat.context", "chat.predict", "chat.options", "chat.stream", "chat.keepalive", "chat.tools.maxdepth",
    "guard.enabled", "rag.enabled"
)

# Characters kept of each text: enough to know what it was about
INPUT_CHARS   : int = 1000
OUTPUT_CHARS  : int = 2000
RESULT_CHARS  : int = 500
ARGUMENT_CHARS: int = 300

def traces_path() -> str:
    """ Where the records go: LOUIS_TRACES, or the file of the settings in the working directory (as louis.db) """
    return os.environ.get("LOUIS_TRACES") or os.path.join(os.getcwd(), default_settings["monitor.file"])

def prompt_version(prompt: str) -> str:
    """ The version of a system prompt: the start of its hash, the same text always gives the same one """
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8]

def text(value, most: int) -> str | None:
    """ A text as it may be kept: cleaned the way the log is (with the guard), then cut to most characters """
    if value is None:
        return None
    value = scrub(value if isinstance(value, str) else str(value))
    return value if len(value) <= most else value[:most] + f"… [+{len(value) - most}]"

def arguments(values: dict) -> dict:
    """ The arguments of a tool call as they are kept: a whole file given to write_file is cut like any text """
    return {key: text(value, ARGUMENT_CHARS) if isinstance(value, str) else value for key, value in values.items()}

def given(messages: list[dict]) -> list[dict]:
    """ What the model is given this time: the messages after its last reply (the request, the results of its calls) """
    last: int = max((i for i, message in enumerate(messages) if message["role"] == "assistant"), default=0)
    return [
        {
            "role": message["role"],
            "content": text(message.get("content"), RESULT_CHARS if message["role"] == "tool" else INPUT_CHARS),
            **({"tool": message["tool_name"]} if message.get("tool_name") else {})
        }
        for message in messages[last + 1:]
    ]

@dataclass
class Turn:
    """ A message of the user being answered: what its records add up to """
    id               : str
    start            : float
    input            : str | None = None
    output           : str        = ""
    model            : str | None = None
    prompt           : str | None = None
    think            : bool       = False
    rounds           : int        = 0
    llm_time         : float      = 0.0
    prompt_tokens    : int        = 0
    completion_tokens: int        = 0
    tools            : int        = 0
    tool_errors      : int        = 0
    guard            : int        = 0
    waited           : float      = 0.0

class Recorder:
    """
        Listens to the bus, as the log does, and writes one record per line in its file. A record is written whole in
        one go, the file opened for it only: two louis sharing the file (the global one of install.sh) never mix lines
    """
    def __init__(self, path: str, settings: dict[str] = default_settings):
        """ Init a recorder writing to path, created on the first record """
        self.__path     : str               = path
        self.__settings : dict[str]         = settings
        self.__run      : str               = uuid.uuid4().hex[:12]
        self.__session  : int | None        = None
        self.__turn     : Turn | None       = None
        # The arguments of the tool call running: TOOL_CALL_ENDED does not repeat them
        self.__arguments: dict              = {}
        # The permission being asked (its id, since when), and the seconds the tool call running waited for the user
        self.__asked    : tuple[int, float] | None = None
        self.__waited   : float             = 0.0
        # The prompts already written whole in this run
        self.__prompts  : set[str]          = set()
        self.__broken   : bool              = False

    @property
    def path(self) -> str:
        """ Get the file the records go to """
        return self.__path

    def bind(self, bus: EventBus) -> "Recorder":
        """ Record what happens on the bus, from now on """
        bus.subscribe(self.__on_started, APP_STARTED)
        bus.subscribe(self.__on_session, SESSION_CREATED, SESSION_SAVED, SESSION_RESUMED)
        bus.subscribe(self.__on_turn_started, CHAT_TURN_STARTED)
        bus.subscribe(self.__on_model_call, MODEL_CALL)
        bus.subscribe(self.__on_tool_started, TOOL_CALL_STARTED)
        # Bound before the interface: the question is timed before the user reads it, the answer as soon as it comes
        bus.subscribe(self.__on_asked, TOOL_BEGFOR_PERMISSION)
        bus.subscribe(self.__on_answered, TOOL_GRANT_PERMISSION)
        bus.subscribe(self.__on_tool_ended, TOOL_CALL_ENDED)
        bus.subscribe(self.__on_guard, GUARD_TRIGGERED)
        bus.subscribe(self.__on_structured, STRUCTURED_REPLY)
        bus.subscribe(self.__on_retrieved, RAG_RETRIEVED)
        bus.subscribe(self.__on_turn_ended, CHAT_TURN_ENDED)
        return self

    def __on_started(self, event: Event) -> None:
        """ The run: which model, and how it is set up """
        self.__write(
            "run",
            model=event.data["model"],
            think=event.data["think"],
            cwd=os.getcwd(),
            settings={key: self.__settings.get(key) for key in RUN_SETTINGS}
        )

    def __on_session(self, event: Event) -> None:
        """ The session the next records belong to: a new one has no id until the user writes in it """
        self.__session = None if event.name == SESSION_CREATED else event.data["id"]

    def __on_turn_started(self, event: Event) -> None:
        """ A message of the user: the records until its end belong to its turn """
        self.__turn = Turn(uuid.uuid4().hex[:12], time.perf_counter())

    def __on_model_call(self, event: Event) -> None:
        """ One request to the model, with the prompt it ran on: written whole the first time this run meets it """
        data: dict = event.data
        version: str = prompt_version(data["system"])
        if version not in self.__prompts:
            self.__prompts.add(version)
            self.__write("prompt", prompt=version, chars=len(data["system"]), text=scrub(data["system"]))

        reply: dict = data["reply"] or {}
        turn: Turn | None = self.__turn
        self.__write(
            "llm",
            turn=turn.id if turn else None,
            session=self.__session,
            round=turn.rounds if turn else None,
            model=data["model"],
            prompt=version,
            think=data["think"],
            messages=len(data["messages"]),
            tools=len(data["tools"]),
            input=given(data["messages"]),
            status=data["status"],
            error=data["error"],
            latency=data["latency"],
            ttft=reply.get("ttft"),
            prompt_tokens=reply.get("prompt_tokens", 0),
            completion_tokens=reply.get("completion_tokens", 0),
            load=reply.get("load", 0.0),
            prompt_eval=reply.get("prompt_eval", 0.0),
            generation=reply.get("generation", 0.0),
            done=reply.get("done"),
            output=text(reply.get("content", ""), OUTPUT_CHARS),
            tool_calls=[{"name": call["name"], "arguments": arguments(call["arguments"])}
                        for call in reply.get("tool_calls") or []]
        )
        if turn is None:
            return
        # The request of the user is the last message the first call is given (the nudge comes later)
        if turn.rounds == 0:
            turn.input = next((m.get("content") for m in reversed(data["messages"]) if m["role"] == "user"), None)
        turn.rounds += 1
        turn.model, turn.prompt, turn.think = data["model"], version, data["think"]
        turn.llm_time += data["latency"]
        turn.prompt_tokens += reply.get("prompt_tokens", 0)
        turn.completion_tokens += reply.get("completion_tokens", 0)
        if reply.get("content"):
            turn.output = reply["content"]

    def __on_tool_started(self, event: Event) -> None:
        """ Keep the arguments (masked with the guard, as they are shown) for the end of the call """
        self.__arguments = event.data["arguments"]
        self.__asked, self.__waited = None, 0.0

    def __on_asked(self, event: Event) -> None:
        """ A tool asks the user: from now on, the time is the user's """
        self.__asked = (event.data["id"], time.perf_counter())

    def __on_answered(self, event: Event) -> None:
        """ The user answered: the first answer ends the wait, as it is the one that counts """
        if self.__asked is None or event.data.get("id") != self.__asked[0]:
            return
        waited: float = time.perf_counter() - self.__asked[1]
        self.__asked = None
        self.__waited += waited
        if self.__turn is not None:
            self.__turn.waited += waited

    def __on_tool_ended(self, event: Event) -> None:
        """ One tool call: whether it worked, how long it took, and how much of that it waited for the user """
        data: dict = event.data
        self.__write(
            "tool",
            turn=self.__turn.id if self.__turn else None,
            session=self.__session,
            name=data["name"],
            producer=data["producer"],
            ok=data["ok"],
            duration=data["duration"],
            waited=round(self.__waited, 3),
            arguments=arguments(self.__arguments),
            result=text(data["result"], RESULT_CHARS),
            chars=len(data["result"])
        )
        # A question nobody answered is no wait of the user: without an interface, the tool is refused at once
        self.__arguments, self.__asked, self.__waited = {}, None, 0.0
        if self.__turn is not None:
            self.__turn.tools += 1
            self.__turn.tool_errors += not data["ok"]

    def __on_guard(self, event: Event) -> None:
        """ A rail changed a message: which one, where. Not what it said instead, that is in the log """
        self.__write(
            "guard",
            turn=self.__turn.id if self.__turn else None,
            session=self.__session,
            stage=event.data["stage"],
            action=event.data["action"],
            rails=event.data["rails"],
            tool=event.data.get("tool")
        )
        if self.__turn is not None:
            self.__turn.guard += 1

    def __on_structured(self, event: Event) -> None:
        """ A reply asked as JSON: its schema, whether it matched, after how many replies, and why not """
        self.__write(
            "structured",
            turn=self.__turn.id if self.__turn else None,
            session=self.__session,
            schema=event.data["schema"],
            valid=event.data["valid"],
            attempts=event.data["attempts"],
            errors=[text(error, RESULT_CHARS) for error in event.data["errors"]]
        )

    def __on_retrieved(self, event: Event) -> None:
        """ A look-up in the knowledge base: the query (cleaned as any text), the paths it found, not their text """
        self.__write(
            "rag",
            turn=self.__turn.id if self.__turn else None,
            session=self.__session,
            query=text(event.data["query"], INPUT_CHARS),
            source=event.data["source"],
            mode=event.data["mode"],
            hits=[f"{hit['source']} {hit['path']}:{hit['start']}-{hit['end']}" for hit in event.data["hits"]],
            duration=event.data["duration"]
        )

    def __on_turn_ended(self, event: Event) -> None:
        """ The whole answer: how it ended, how long the user waited, what it cost """
        turn: Turn | None = self.__turn
        if turn is None:
            return
        self.__turn = None
        self.__write(
            "turn",
            turn=turn.id,
            session=self.__session,
            reason=event.data["reason"],
            message=text(event.data.get("message"), OUTPUT_CHARS),
            latency=round(time.perf_counter() - turn.start, 3),
            waited=round(turn.waited, 3),
            model=turn.model,
            prompt=turn.prompt,
            think=turn.think,
            rounds=turn.rounds,
            llm_time=round(turn.llm_time, 3),
            prompt_tokens=turn.prompt_tokens,
            completion_tokens=turn.completion_tokens,
            tools=turn.tools,
            tool_errors=turn.tool_errors,
            guard=turn.guard,
            input=text(turn.input, INPUT_CHARS),
            output=text(turn.output, OUTPUT_CHARS)
        )

    def __write(self, kind: str, **fields) -> None:
        """ Append one record. A file that can not be written stops the recording, told once: louis goes on without """
        if self.__broken:
            return
        record: dict = {
            "v": VERSION,
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "type": kind,
            "run": self.__run,
            **fields
        }
        try:
            with open(self.__path, "a", encoding="utf-8") as file:
                file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError as e:
            self.__broken = True
            log.warning(f"[monitor] cannot write to {self.__path} ({e.strerror}): the calls are not recorded any more")
