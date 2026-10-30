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
##   step    a step of the reasoning loop (/react): what the model thought, the tools it called
##   check   the check of a draft of the reasoning loop: whether it went, its problems, whether it was written again
##   plan    the plan of a risky reply shown to the user (/plan): its actions and their risk, whether it was approved,
##           what the user answered, how long they took to decide (waited)
## An llm record tells what the call was for (purpose): a reply, JSON, the check of a draft, a summary of the context.
## Only the replies make the rounds and the output of a turn: the JSON of a check is no answer
##   cache   a question looked up in the semantic cache (cache/): whether its answer was there, how close the closest
##           one was, how long it took, or why it was not looked up. A turn answered from the cache is cached: no llm record
##   eval    an answer judged (eval/): its scores, and the claims its sources do not support. Written by the thread of
##           the judge, once the turn is over: it names the answer by the session, the prompt and the model instead
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
from events.event_list import REASONING_STEP, REASONING_CHECK, EVAL_SCORED, CACHE_LOOKUP, CACHE_HIT, PLAN_PROPOSED, PLAN_DECIDED
from config.settings import settings as default_settings
from config.prompt import REACT_PROMPT
from logger.logger import log, scrub
import hashlib
import json
import os
import threading
import time
import uuid

# Bumped when a field changes its meaning: the metrics can tell the old records apart
VERSION: int = 1

# The settings that change the latency or the tokens of a reply: kept with each run, to explain a drift
RUN_SETTINGS: tuple[str, ...] = (
    "chat.context", "chat.predict", "chat.options", "chat.stream", "chat.keepalive", "chat.tools.maxdepth", "guard.enabled",
    "rag.enabled", "rag.rerank.enabled", "rag.rerank.model", "rag.rerank.pool", "rag.rerank.min_score",
    "rag.rerank.max_chars", "rag.embed.gpu", "eval.enabled", "eval.model", "cache.enabled", "cache.threshold",
    "cache.rerank.enabled", "cache.rerank.min_score", "cache.seed.min_score", "cache.match.model", "hitl.enabled", "hitl.level"
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
    # The reasoning loop (/react): its steps, the checks of its drafts, the drafts written again, and whether the
    # answer was given with problems left
    react            : bool       = False
    steps            : int        = 0
    checks           : int        = 0
    revised          : int        = 0
    left             : bool       = False
    # Answered from the semantic cache, without the model
    cached           : bool       = False
    # The plans of the turn shown to the user, and those they did not approve (refused, or left without an answer)
    plans            : int        = 0
    refused_plans    : int        = 0

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
        # The plan being shown: its id, since when, and its actions (their tool and their risk)
        self.__plan     : tuple[int, float, list[dict]] | None = None
        # The judge writes from its own thread: one record at a time
        self.__lock     : threading.Lock    = threading.Lock()

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
        bus.subscribe(self.__on_plan_proposed, PLAN_PROPOSED)
        bus.subscribe(self.__on_plan_decided, PLAN_DECIDED)
        bus.subscribe(self.__on_tool_ended, TOOL_CALL_ENDED)
        bus.subscribe(self.__on_guard, GUARD_TRIGGERED)
        bus.subscribe(self.__on_structured, STRUCTURED_REPLY)
        bus.subscribe(self.__on_step, REASONING_STEP)
        bus.subscribe(self.__on_check, REASONING_CHECK)
        bus.subscribe(self.__on_retrieved, RAG_RETRIEVED)
        bus.subscribe(self.__on_lookup, CACHE_LOOKUP)
        bus.subscribe(self.__on_cache_hit, CACHE_HIT)
        bus.subscribe(self.__on_turn_ended, CHAT_TURN_ENDED)
        bus.subscribe(self.__on_eval, EVAL_SCORED)
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
        # Older traces have no purpose: every call was a reply then
        purpose: str = data.get("purpose", "reply")
        self.__write(
            "llm",
            turn=turn.id if turn else None,
            session=self.__session,
            round=turn.rounds if turn else None,
            purpose=purpose,
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
        # Every call costs the turn, only the replies make it: a check or a summary is no round, nor its answer
        turn.llm_time += data["latency"]
        turn.prompt_tokens += reply.get("prompt_tokens", 0)
        turn.completion_tokens += reply.get("completion_tokens", 0)
        if purpose not in ("reply", "structured"):
            return
        # The request of the user is the last message the first call is given (the nudge comes later), without how
        # the reasoning loop told it to reason
        if turn.rounds == 0:
            asked: str | None = next((m.get("content") for m in reversed(data["messages"]) if m["role"] == "user"), None)
            turn.input = asked.removesuffix(REACT_PROMPT) if asked else asked
        turn.rounds += 1
        turn.model, turn.prompt, turn.think = data["model"], version, data["think"]
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

    def __on_step(self, event: Event) -> None:
        """ A step of the reasoning loop: what the model thought before it acted, and the tools it called """
        if self.__turn is not None:
            self.__turn.react = True
            self.__turn.steps += 1
        self.__write(
            "step",
            turn=self.__turn.id if self.__turn else None,
            session=self.__session,
            step=event.data["step"],
            thought=text(event.data["thought"], INPUT_CHARS),
            tools=event.data["tools"]
        )

    def __on_check(self, event: Event) -> None:
        """ The check of a draft: whether it went, what was wrong with it, whether it was written again """
        data: dict = event.data
        if self.__turn is not None:
            self.__turn.checks += 1
            self.__turn.revised += data["revise"]
            self.__turn.left = not data["ok"] and not data["revise"]
        self.__write(
            "check",
            turn=self.__turn.id if self.__turn else None,
            session=self.__session,
            attempt=data["attempt"],
            ok=data["ok"],
            revise=data["revise"],
            problems=[text(problem, RESULT_CHARS) for problem in data["problems"]]
        )

    def __on_retrieved(self, event: Event) -> None:
        """
            A look-up in the knowledge base: the query (cleaned as any text), the paths it found with their scores, not
            their text. With the reranker, its score and the index's (fused) both: what the reranker changed, how much
            it dropped, and how long it took, to tune its threshold and its pool
        """
        data: dict = event.data
        self.__write(
            "rag",
            turn=self.__turn.id if self.__turn else None,
            session=self.__session,
            query=text(data["query"], INPUT_CHARS),
            source=data["source"],
            # Whether the model filters, and how: what its description and its size change
            path=data.get("path"),
            kind=data.get("kind"),
            after=data.get("after"),
            files=data.get("files"),
            mode=data["mode"],
            reranker=data.get("reranker"),
            candidates=data.get("candidates"),
            dropped=data.get("dropped", 0),
            hits=[f"{hit['source']} {hit['path']}:{hit['start']}-{hit['end']}" for hit in data["hits"]],
            scores=[hit["score"] for hit in data["hits"]],
            fused=[hit.get("fused") for hit in data["hits"]] if data.get("reranker") else None,
            rerank=data.get("rerank"),
            duration=data["duration"]
        )

    def __on_lookup(self, event: Event) -> None:
        """ A question looked up in the semantic cache, or why it was not """
        data: dict = event.data
        self.__write(
            "cache",
            turn=self.__turn.id if self.__turn else None,
            session=self.__session,
            hit=data["hit"],
            score=data["score"],
            duration=data["duration"],
            reason=data["reason"],
            matched=data.get("matched", 0)
        )

    def __on_cache_hit(self, event: Event) -> None:
        """ The turn is answered from the cache: its latency is not the model's """
        if self.__turn is not None:
            self.__turn.cached = True

    def __on_plan_proposed(self, event: Event) -> None:
        """ A plan shown to the user: from now on, the time is theirs """
        actions: list[dict] = [{"tool": action["tool"], "risk": action["risk"]} for action in event.data["actions"]]
        self.__plan = (event.data["id"], time.perf_counter(), actions)

    def __on_plan_decided(self, event: Event) -> None:
        """ The user decided: the first answer counts, as it is the one the app keeps """
        if self.__plan is None or event.data.get("id") != self.__plan[0]:
            return
        self.__write_plan(True, event.data.get("approved") is True, event.data.get("feedback") or "")

    def __write_plan(self, answered: bool, approved: bool, feedback: str) -> None:
        """ The plan shown, once decided, or once its turn ended without an answer (a script, Ctrl+C): refused """
        _, start, actions = self.__plan
        self.__plan = None
        waited: float = time.perf_counter() - start
        if self.__turn is not None:
            self.__turn.waited += waited
            self.__turn.plans += 1
            self.__turn.refused_plans += not approved
        risks: list[str] = [action["risk"] for action in actions]
        self.__write(
            "plan",
            turn=self.__turn.id if self.__turn else None,
            session=self.__session,
            actions=actions,
            irreversible=risks.count("irreversible"),
            answered=answered,
            approved=approved,
            feedback=text(feedback, RESULT_CHARS) if feedback else None,
            waited=round(waited, 3)
        )

    def __on_turn_ended(self, event: Event) -> None:
        """ The whole answer: how it ended, how long the user waited, what it cost """
        if self.__plan is not None:
            self.__write_plan(False, False, "")
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
            output=text(turn.output, OUTPUT_CHARS),
            react=turn.react,
            steps=turn.steps,
            checks=turn.checks,
            revised=turn.revised,
            left=turn.left,
            plans=turn.plans,
            refused_plans=turn.refused_plans,
            cached=turn.cached
        )

    def __on_eval(self, event: Event) -> None:
        """
            An answer judged: its scores, and the claims the sources do not support (cut as any text). From the thread
            of the judge: only the data of the event is read, never the turn running
        """
        data: dict = event.data
        claims: list[dict] = data["claims"]
        self.__write(
            "eval",
            sample=data["id"],
            session=data["session"],
            model=data["model"],
            prompt=data["prompt"],
            judge=data["judge"],
            status=data["status"],
            error=data["error"],
            faithfulness=data["faithfulness"],
            relevance=data["relevance"],
            coherence=data["coherence"],
            claims=len(claims),
            supported=sum(1 for claim in claims if claim["verdict"] == "supported"),
            contradicted=sum(1 for claim in claims if claim["verdict"] == "contradicted"),
            unverifiable=sum(1 for claim in claims if claim["verdict"] == "unverifiable"),
            flagged=[{"claim": text(claim["text"], ARGUMENT_CHARS), "verdict": claim["verdict"], "source": claim["source"]}
                     for claim in claims if claim["verdict"] != "supported"],
            sources=[f"{source['tool']} {json.dumps(arguments(source['arguments']), ensure_ascii=False, default=str)}"
                     for source in data["sources"]],
            duration=data["duration"],
            # Where the time of the judge went: a load is a reload of the model (another num_ctx, another model)
            requests=data["spent"]["requests"],
            load=data["spent"]["load"],
            generation=data["spent"]["generation"],
            prompt_tokens=data["spent"]["prompt_tokens"],
            completion_tokens=data["spent"]["completion_tokens"],
            input=text(data["question"], INPUT_CHARS)
        )

    def __write(self, kind: str, **fields) -> None:
        """ Append one record. A file that can not be written stops the recording, told once: louis goes on without """
        with self.__lock:
            self.__append(kind, fields)

    def __append(self, kind: str, fields: dict) -> None:
        """ Append one record, under the lock """
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
