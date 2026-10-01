##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## App Class (the manager)
##

from interface.interface import Interface
from model.model import OllamaModel
from model.model_exception import ModelException
from model.reply import Reply
from tool.tool_manager import ToolManager
from tool.tool import Tool, failed
from tool.tool_call import ToolCall
from tool.impl.file.tool_tree import TreeTool
from tool.impl.file.tool_cat import CatTool
from tool.impl.file.tool_edit import EditTool
from tool.impl.file.tool_write import WriteTool
from tool.impl.file.tool_search import SearchTool
from tool.impl.file.tool_mkdir import MkdirTool
from tool.impl.web.tool_websearch import InternetTool
from tool.impl.git.tool_git import GitTool
from tool.impl.git.tool_pr import PullRequestTool
from tool.permission import PermissionManager
from guard.guard import Guard
from guard.verdict import Verdict
from tool.seen_files import SeenFiles
from app.context_window import ContextWindow, capped, share, MAX_RESULT, ROUND
from events.event_bus import EventBus, Event
from events.event_list import *
from logger.logger import log, log_event
from config.prompt import NUDGE_PROMPT
from session.user import User
from session.session import Session
from command.command import CommandTree
from command.impl.command_clear import ClearCommand
from command.impl.command_think import ToggleThinkCommand
from command.impl.command_sessions import SessionsCommand
from command.impl.command_resume import ResumeCommand
from monitor.recorder import Recorder
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict
from datetime import date
import json
import os
import re
import time

# A reply that says what the model is about to do, in French or English. In French, "je vais" must lead to
# a verb ("je vais créer", "je vais d'abord lire"): "je vais bien" is only small talk, as "let me know" is.
# "Vérifions game.py" too, but only at the start of a sentence: "ici, nous vérifions que..." explains the code
ANNOUNCE: re.Pattern = re.compile(
    r"\b(?:je vais (?:[\w']+ ){0,2}?[\w']+(?:er|ir|re|oir)|je m'apprête à|laisse-moi"
    r"|i will|i'll|let me(?! know)|let's|i am going to|i'm going to)\b"
    r"|(?:^|(?<=[.!?:] ))(?:vérifi|regard|lis|ajout|corrige|modifi|examin|cherch|cré|consult|voy|commenç"
    r"|analys|ouvr|test|remplaç|renomm)ons\b",
    re.IGNORECASE | re.MULTILINE
)

# Logged whole elsewhere (the reply and its stats by the model, the tool calls by __call): not once more per event
UNLOGGED: frozenset[str] = frozenset({
    CHAT_TEXT, CHAT_THINKING, CHAT_REPLY, MODEL_CALL, TOOL_CALL_STARTED, TOOL_CALL_ENDED
})

# Where the context Louis adds starts, after the system prompt
CONTEXT: str = "\n\n# Contexte\n"

CANCELLED_TOOL: str = "Annulé : l'utilisateur a interrompu Louis avant la fin de cet outil."

# The same call (tool and arguments) made this many times already for a message is refused: the model goes round in
# circles. After MAX_REFUSED refused calls, the turn stops
SAME_CALLS : int = 2
MAX_REFUSED: int = 3
REPEATED_CALL: str = (
    "Erreur : tu as déjà fait exactement cet appel 2 fois pour cette demande. N'en refais pas un troisième : "
    "utilise ce que tu sais déjà, lis une autre partie, ou réponds à l'utilisateur."
)
# The model sometimes asks for dozens of calls at once, often the same ones again (a list gone wrong): the first
# MAX_CALLS different ones are kept, the others never made. And the results of a round, never cut by the window, must
# still have this share of the context for one more call to run
MAX_CALLS: int   = 6
MIN_ROOM : float = 0.05
IGNORED_CALLS: str = (
    "\n[{} autres appels de ta réponse ont été ignorés (en double, ou trop nombreux à la fois) : "
    "refais ceux qui manquent dans ta prochaine réponse.]"
)
NO_ROOM: str = (
    "Erreur : les résultats de ta réponse prennent déjà trop de place dans le contexte : cet appel n'a pas été fait. "
    "Refais-le dans ta prochaine réponse."
)
LOOP_MESSAGE: str = (
    "Louis tournait en rond (les mêmes appels d'outils, encore et encore) : arrêté. Reformule ou découpe la demande."
)

# Calls of a tool the guard refuses in a turn before the tool is withdrawn until the next message: the model
# may redo a call without the sensitive data once, but qwen3 can also ask the same one again and again
REFUSED_CALLS: int = 2

class App:
    """ App Class: runs the conversation, and tells everything through the bus, never printing itself """
    def __init__(self, settings: dict[str], system_prompt: str, user: User, stream: Interface,
                 monitor: Recorder | None = None):
        """
            Init the Application class, on a new session of the user, shown by the interface stream.
            With a monitor, every call to the model and to the tools is recorded, for the metrics
        """
        self.__settings: dict[str] = settings
        self.__user: User = user
        self.__system_prompt: str = system_prompt
        self.__think: bool = bool(settings.get("chat.think", False))

        self.__bus: EventBus = EventBus()
        # Subscribed first: an event is logged before any other handler reacts to it
        self.__bus.subscribe(lambda event: event.name in UNLOGGED or log_event(event))
        # Before APP_STARTED: the run is recorded with its model
        if monitor is not None:
            monitor.bind(self.__bus)
        # The interface asks the user (TOOL_BEGFOR_PERMISSION) and answers (TOOL_GRANT_PERMISSION)
        self.__permissions: PermissionManager = PermissionManager(self.__bus)

        self.__toolManager: ToolManager = ToolManager()\
            .register(TreeTool())\
            .register(CatTool())\
            .register(EditTool())\
            .register(WriteTool())\
            .register(SearchTool())\
            .register(MkdirTool())\
            .register(InternetTool())\
            .register(GitTool())\
            .register(PullRequestTool())\

        log.info(f"[app] tools: {', '.join(tool['function']['name'] for tool in self.__toolManager.all())}")

        # What the model sees of the session: cut down before it overflows the context, instead of Ollama cutting it
        self.__window: ContextWindow = ContextWindow(settings.get("chat.context", 12288), self.__toolManager.all())
        # The files read in another session are not in the history of this one: they must be read again to be edited
        self.__seen_files: SeenFiles = SeenFiles()
        self.__bus.subscribe(self.__on_session_changed, SESSION_CREATED, SESSION_RESUMED)

        self.__commands: CommandTree = CommandTree()\
            .register(ClearCommand())\
            .register(SessionsCommand())\
            .register(ResumeCommand())\
            .register(ToggleThinkCommand())\

        # NOTE: Raisable
        self.__model : OllamaModel = OllamaModel(settings["chat.uri"], f"{settings["chat.model.name"]}:{settings["chat.model.parameters"]}")

        # NOTE: Raisable. Loaded after the model: a model that does not answer fails before NeMo takes its time to load
        self.__guard: Guard | None = Guard(self.__bus) if settings.get("guard.enabled", False) else None
        # The calls the guard refused in the current turn, by tool: counted again from 0 on each message
        self.__refused: Counter[str] = Counter()

        self.__stream: Interface = stream
        # The interface shows what happens (the conversation, the commands...) by listening to the bus
        self.__stream.bind(self.__bus)
        self.__bus.dispatch(
            APP_STARTED,
            model=self.__model.model,
            think=self.think,
            commands=[command.describe() for command in self.__commands.commands]
        )

        # Started once the model answers: a failed start leaves no empty session behind
        self.new_session()

    @property
    def stream(self) -> Interface:
        """ Get the current stream (interface) """
        return self.__stream

    @property
    def events(self) -> EventBus:
        """ Get the event bus: dispatch there what the user must know, the interfaces show it """
        return self.__bus

    @property
    def user(self) -> User:
        """ Get the user talking to Louis """
        return self.__user

    @property
    def session(self) -> Session:
        """ Get the current session of the user, where the conversation is kept """
        return self.__user.current_session

    @property
    def model(self) -> OllamaModel:
        """ Returns the current model """
        return self.__model

    @property
    def think(self) -> bool:
        """ Returns if thinking is activate """
        return self.__think and self.model.thinking

    @think.setter
    def think(self, state: bool) -> None:
        """ Set the current thinking mode, for the next requests """
        if self.model.thinking:
            self.__think = state

    def new_session(self, system_prompt: str | None = None) -> Session:
        """ Start a new session of the user, on the given system prompt or on the one Louis started with """
        session: Session = self.__user.new_session(os.getcwd())
        session.add("system", (system_prompt or self.__system_prompt).rstrip() + self.__context())
        self.__bus.dispatch(
            SESSION_CREATED,
            user=self.__user.name,
            persistent=not self.__user.is_anonymous,
            custom_prompt=bool(system_prompt)
        )
        self.__estimate_context()
        return session

    def __context(self) -> str:
        """
            What the model can not guess, put after its prompt: the user, and the date (for web_search). Never the
            folder of the project: the model gives its name to the tools as a path, which they do not find
        """
        lines: list[str] = [f"- Date : {date.today().isoformat()}"]
        if not self.__user.is_anonymous:
            lines.insert(0, f"- Utilisateur : {self.__user.name}")
        return CONTEXT + "\n".join(lines) + "\n"

    def __prompt(self) -> str:
        """ The system prompt of the current session, without the context put after it: the date changes it every day """
        messages = self.session.messages
        if not messages or messages[0].role != "system":
            return ""
        prompt, found, _ = messages[0].content.rpartition(CONTEXT)
        return prompt if found else messages[0].content

    def __on_session_changed(self, event: Event) -> None:
        """ Another session: nothing of it is cut or read yet. A resumed one fills the context with its history """
        self.__window.reset()
        self.__seen_files.clear()
        if event.name == SESSION_RESUMED:
            self.__estimate_context()

    def __estimate_context(self) -> None:
        """ Tell how full the context is with the current session, as it will be sent, before the model measures it """
        messages, _ = self.__window.view(self.session.history)
        self.__bus.dispatch(CHAT_CONTEXT, used=self.__window.tokens(messages), size=self.__window.size, estimated=True)

    def __view(self) -> list[dict]:
        """ The session as the model sees it: its old tool results cut down, and told, once the context fills up """
        messages, cut = self.__window.view(self.session.history)
        if cut:
            used: int = self.__window.tokens(messages)
            log.info(f"[app] context cut down: {cut['results']} tool results, {cut['dropped']} messages left out, "
                     f"{used} tokens left of {self.__window.size}")
            self.__bus.dispatch(CHAT_COMPACTED, **cut, used=used, size=self.__window.size)
            self.__bus.dispatch(CHAT_CONTEXT, used=used, size=self.__window.size, estimated=True)
        return messages

    @property
    def settings(self) -> dict[str]:
        """ Get the settings Louis runs with, for the tools to read theirs """
        return self.__settings

    @property
    def permissions(self) -> PermissionManager:
        """ Get the permission manager, for the tools to ask before acting """
        return self.__permissions

    @property
    def seen_files(self) -> SeenFiles:
        """ Get the files the model has read or written in this session, for edit_file to check """
        return self.__seen_files

    def run(self) -> int:
        """ Run the application: answer the messages of the user, until the input ends or Ctrl+C there """
        while True:
            try:
                u = self.stream.getUserInput()
            except (KeyboardInterrupt, EOFError) as e:
                log.info(f"[app] closed by the user ({type(e).__name__})")
                self.__bus.dispatch(APP_STOPPED, reason="interrupt" if isinstance(e, KeyboardInterrupt) else "eof")
                return 0
            if not u.strip():
                continue
            log.info(f"[user] {u.strip()}")
            try:
                if not self.__commands.fetch(u, self):
                    self.__answer(u)
            except KeyboardInterrupt:
                # Ctrl+C in a command: back to the input, the answers handle it themselves
                log.info("[app] command interrupted by the user")

    def __answer(self, text: str) -> None:
        """
            Answer a message of the user: the model replies, calling tools, until a reply calls none.
            With the guard, the model only reads what the input rails let through, and the user only
            reads what the output rails let through. Whatever goes wrong in the guard ends the turn:
            a guard that cannot check never lets a message go unchecked
        """
        self.__bus.dispatch(CHAT_TURN_STARTED)
        rounds: int = self.__settings.get("chat.tools.maxdepth", 8)
        # The calls of the last reply not answered yet: each of them must get an answer, even if cancelled
        pending: list[ToolCall] = []
        nudged: bool = False
        # A reply can only be checked whole: with the guard, it is shown once checked, not as it is written
        stream: Callable | None = None if self.__guard else lambda chunk: self.__bus.dispatch(CHAT_TEXT, text=chunk)
        self.__refused.clear()
        # The calls made for this message, and those refused for being the same again: the model goes round in circles
        made: Counter = Counter()
        repeats: int = 0
        try:
            question: str = text
            if self.__guard is not None:
                verdict: Verdict = self.__guard.check_input(text)
                # Refused: kept out of the session, the model would read it again on the next message
                if verdict.refused:
                    self.__bus.dispatch(CHAT_TURN_ENDED, reason="refused", message=verdict.content)
                    return
                question = verdict.content

            saved: bool = self.session.saved
            self.session.add("user", question)
            if not saved and self.session.saved:
                self.__bus.dispatch(SESSION_SAVED, id=self.session.id)

            for _ in range(rounds):
                reply: Reply = self.__chat(
                    self.__view(),
                    [tool for tool in self.__toolManager.all() if self.__refused[tool["function"]["name"]] < REFUSED_CALLS],
                    stream
                )
                calls: list[ToolCall] = []
                for call in reply.tool_calls:
                    if call not in calls and len(calls) < MAX_CALLS:
                        calls.append(call)
                ignored: int = len(reply.tool_calls) - len(calls)
                if ignored:
                    log.warning(f"[app] {len(reply.tool_calls)} calls in one reply: {ignored} ignored")
                reply.tool_calls = calls
                if self.__guard is not None and reply.content:
                    self.__screen(question, reply)
                self.session.add("assistant", reply.content, tool_calls=reply.tool_calls)
                # Without the counts of Ollama (a reply cut short), the last known value stays
                if reply.tokens:
                    self.__bus.dispatch(
                        CHAT_CONTEXT, used=reply.tokens, size=self.__settings.get("chat.context", 12288), estimated=False
                    )
                self.__bus.dispatch(CHAT_REPLY, content=reply.content, tools=[call.name for call in reply.tool_calls])
                if reply.cut and not reply.tool_calls:
                    log.warning("[app] the reply reached the most tokens it may take: cut")
                    self.__bus.dispatch(CHAT_TURN_ENDED, reason="length", message=(
                        f"Réponse coupée : le modèle a dépassé {self.__settings.get('chat.predict')} tokens sans finir "
                        "(il tournait peut-être en rond). Demande une partie plus petite."
                    ))
                    return

                if not reply.tool_calls:
                    # Once per message, so a wrong guess costs one round and never loops
                    if nudged or not ANNOUNCE.search(reply.content):
                        self.__bus.dispatch(CHAT_TURN_ENDED, reason="done", message=None)
                        return
                    nudged = True
                    log.info("[app] the model announced an action without calling a tool: nudging it")
                    self.__bus.dispatch(CHAT_NUDGED)
                    self.session.add("user", NUDGE_PROMPT)
                    continue

                pending = list(reply.tool_calls)
                # The share of the context the results of this round may still take
                room: float = ROUND
                while pending:
                    call: ToolCall = pending[0]
                    key: str = f"{call.name} {json.dumps(call.arguments, sort_keys=True, ensure_ascii=False, default=str)}"
                    reason: str | None = None
                    if made[key] >= SAME_CALLS:
                        reason = REPEATED_CALL
                        repeats += 1
                    elif room < MIN_ROOM:
                        reason = NO_ROOM
                    else:
                        made[key] += 1
                    result: str = self.__call(call, refused=reason, most=min(MAX_RESULT, room))
                    room -= share(result, self.__window.size)
                    if ignored and len(pending) == 1:
                        result += IGNORED_CALLS.format(ignored)
                    self.session.add("tool", result, tool_name=call.name)
                    pending.pop(0)
                if repeats >= MAX_REFUSED:
                    log.warning(f"[app] {repeats} calls refused for being the same again: the model goes round in circles")
                    self.__bus.dispatch(CHAT_TURN_ENDED, reason="loop", message=LOOP_MESSAGE)
                    return
        except KeyboardInterrupt:
            for call in pending:
                self.session.add("tool", CANCELLED_TOOL, tool_name=call.name)
            log.info("[app] turn cancelled by the user")
            self.__bus.dispatch(CHAT_TURN_ENDED, reason="cancelled", message=None)
            return
        except ModelException as e:
            log.error(f"[app] the model failed: {e.message}")
            self.__bus.dispatch(CHAT_TURN_ENDED, reason="error", message=e.message)
            return
        except Exception as e:
            log.exception("[app] the turn failed")
            self.__bus.dispatch(CHAT_TURN_ENDED, reason="error", message=f"Erreur interne : {type(e).__name__}: {e}")
            return

        log.warning(f"[app] stopped after {rounds} rounds of tool calls")
        self.__bus.dispatch(CHAT_TURN_ENDED, reason="rounds", message=f"Arrêté après {rounds} tours d'appels d'outils.")

    def __chat(self, messages: list[dict], tools: list[dict], stream: Callable | None) -> Reply:
        """
            Ask the model for its next reply, and tell how the request went (MODEL_CALL), even when it fails or the
            user cancels it: the monitoring records every call, with its latency and its tokens
        """
        start: float = time.perf_counter()
        reply: Reply | None = None
        status, error = "ok", None
        try:
            reply = self.__model.chat(
                messages, tools, think=self.think, on_text=stream,
                on_thinking=lambda chunk: self.__bus.dispatch(CHAT_THINKING, text=chunk)
            )
            return reply
        except ModelException as e:
            status, error = "error", e.message
            raise
        except KeyboardInterrupt:
            status = "cancelled"
            raise
        except Exception as e:
            status, error = "error", f"{type(e).__name__}: {e}"
            raise
        finally:
            self.__bus.dispatch(
                MODEL_CALL,
                model=self.__model.model,
                system=self.__prompt(),
                messages=messages,
                tools=[tool["function"]["name"] for tool in tools],
                think=self.think,
                status=status,
                error=error,
                latency=round(time.perf_counter() - start, 3),
                # A copy: the app changes the reply afterwards (the calls kept, the guard's mask)
                reply=asdict(reply) if reply is not None else None
            )

    def __screen(self, question: str, reply: Reply) -> None:
        """
            Put the reply through the output rails, then show it: masked, or replaced by the refusal.
            Kept in the session as it is shown, so the model never reads again what the user could not.
            A refused reply calls no tool: what the model meant to do with it is not known
        """
        verdict: Verdict = self.__guard.check_output(question, reply.content)
        reply.content = verdict.content
        if verdict.refused:
            reply.tool_calls = []
        self.__bus.dispatch(CHAT_TEXT, text=reply.content)

    def __screen_call(self, call: ToolCall, producer: str) -> str | None:
        """
            Put a call of the model through the tool rails before it runs: the refusal to give back as its
            result, or None to run it. The calls of the user and of Louis are not the model's: they go through.
            A guard that cannot check refuses: an unchecked call never runs
        """
        if self.__guard is None or producer != "model":
            return None
        try:
            verdict: Verdict = self.__guard.check_tool_call(call)
        except Exception as e:
            log.exception(f"[guard] the check of {call.name} failed")
            return (f"Erreur : le garde-fou n'a pas pu vérifier l'appel à '{call.name}' ({type(e).__name__}), "
                    "il n'a pas été lancé.")
        if not verdict.refused:
            return None
        self.__refused[call.name] += 1
        if self.__refused[call.name] >= REFUSED_CALLS:
            log.info(f"[guard] {call.name} refused {REFUSED_CALLS} times: withdrawn until the next message")
        return verdict.content

    def __call(self, call: ToolCall, producer: str = "model", *, refused: str | None = None,
               most: float = MAX_RESULT) -> str:
        """
            Run a tool, asked for by producer ("model", "user" or "system"): whatever goes wrong comes back
            as text, for the model to react. A call refused by the app is not run: refused is its result. The result
            takes at most the share most of the context
        """
        # With the guard, the interfaces show the arguments masked, as the replies are
        shown: dict = self.__guard.hide(call.arguments) if self.__guard is not None else call.arguments
        self.__bus.dispatch(TOOL_CALL_STARTED, name=call.name, arguments=shown, producer=producer)
        log.info(f"[tool] {call.name} {json.dumps(call.arguments, ensure_ascii=False)}")
        start: float = time.perf_counter()
        tool: Tool | None = self.__toolManager.get(call.name)
        if refused is not None:
            result = refused
        elif tool is None:
            names: str = ", ".join(schema["function"]["name"] for schema in self.__toolManager.all())
            result = f"Erreur : l'outil '{call.name}' n'existe pas. Les outils disponibles sont : {names}."
        elif (refusal := self.__screen_call(call, producer)) is not None:
            result = refusal
        else:
            try:
                result = tool.handle(self, **call.arguments)
            except Exception as e:
                log.exception(f"[tool] {call.name} failed")
                result = (f"Erreur : l'outil '{call.name}' a échoué ({type(e).__name__} : {e}). "
                          "Vérifie tes arguments, ou fais autrement.")
        result = result if isinstance(result, str) else str(result)
        # Never more than its share of the context: a whole big file would push the rest of the conversation out
        if refused is None:
            result = capped(result, self.__window.size, most)
        # Unknown, crashed, or it could not do it (a text not found, a permission refused...): not ok
        ok: bool = not failed(result)
        duration: float = time.perf_counter() - start
        log.info(f"[tool] {call.name} done in {duration:.2f}s:\n{result}")
        self.__bus.dispatch(
            TOOL_CALL_ENDED, name=call.name, producer=producer, ok=ok, result=result, duration=round(duration, 3)
        )
        return result
