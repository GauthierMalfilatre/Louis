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
from tool.tool import Tool
from tool.tool_call import ToolCall
from tool.impl.file.tool_tree import TreeTool
from tool.impl.file.tool_cat import CatTool
from tool.impl.file.tool_edit import EditTool
from tool.impl.file.tool_write import WriteTool
from tool.impl.file.tool_search import SearchTool
from tool.impl.file.tool_mkdir import MkdirTool
from tool.impl.web.tool_websearch import InternetTool
from tool.permission import PermissionManager
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
import json
import os
import re
import time

# A reply that says what the model is about to do, in French or English. In French, "je vais" must lead to
# a verb ("je vais créer", "je vais d'abord lire"): "je vais bien" is only small talk
ANNOUNCE: re.Pattern = re.compile(
    r"\b(?:je vais (?:[\w']+ ){0,2}?[\w']+(?:er|ir|re|oir)|je m'apprête à|laisse-moi"
    r"|i will|i'll|let me|i am going to|i'm going to)\b",
    re.IGNORECASE
)

# Logged whole elsewhere (the reply by the model, the tool calls by __call): not once more per event
UNLOGGED: frozenset[str] = frozenset({CHAT_TEXT, CHAT_REPLY, TOOL_CALL_STARTED, TOOL_CALL_ENDED})

CANCELLED_TOOL: str = "Annulé : l'utilisateur a interrompu Louis avant la fin de cet outil."

class App:
    """ App Class: runs the conversation, and tells everything through the bus, never printing itself """
    def __init__(self, settings: dict[str], system_prompt: str, user: User, stream: Interface):
        """ Init the Application class, on a new session of the user, shown by the interface stream """
        self.__settings: dict[str] = settings
        self.__user: User = user
        self.__system_prompt: str = system_prompt
        self.__think: bool = bool(settings.get("chat.think", False))

        self.__bus: EventBus = EventBus()
        # Subscribed first: an event is logged before any other handler reacts to it
        self.__bus.subscribe(lambda event: event.name in UNLOGGED or log_event(event))

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

        log.info(f"[app] tools: {', '.join(tool['function']['name'] for tool in self.__toolManager.all())}")

        self.__commands: CommandTree = CommandTree()\
            .register(ClearCommand())\
            .register(SessionsCommand())\
            .register(ResumeCommand())\
            .register(ToggleThinkCommand())\

        # NOTE: Raisable
        self.__model : OllamaModel = OllamaModel(settings["chat.uri"], f"{settings["chat.model.name"]}:{settings["chat.model.parameters"]}")

        self.__stream: Interface = stream
        # The interface shows what happens (the conversation, the commands...) by listening to the bus
        self.__stream.bind(self.__bus)

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
        session.add("system", system_prompt or self.__system_prompt)
        self.__bus.dispatch(
            SESSION_CREATED,
            user=self.__user.name,
            persistent=not self.__user.is_anonymous,
            custom_prompt=bool(system_prompt)
        )
        return session

    @property
    def permissions(self) -> PermissionManager:
        """ Get the permission manager, for the tools to ask before acting """
        return self.__permissions

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
        """ Answer a message of the user: the model replies, calling tools, until a reply calls none """
        saved: bool = self.session.saved
        self.session.add("user", text)
        if not saved and self.session.saved:
            self.__bus.dispatch(SESSION_SAVED, id=self.session.id)

        self.__bus.dispatch(CHAT_TURN_STARTED)
        rounds: int = self.__settings.get("chat.tools.maxdepth", 8)
        # The calls of the last reply not answered yet: each of them must get an answer, even if cancelled
        pending: list[ToolCall] = []
        nudged: bool = False
        try:
            for _ in range(rounds):
                reply: Reply = self.__model.chat(
                    self.session.history,
                    self.__toolManager.all(),
                    think=self.think,
                    on_text=lambda chunk: self.__bus.dispatch(CHAT_TEXT, text=chunk)
                )
                self.session.add("assistant", reply.content, tool_calls=reply.tool_calls)
                self.__bus.dispatch(CHAT_REPLY, content=reply.content, tools=[call.name for call in reply.tool_calls])

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
                while pending:
                    self.session.add("tool", self.__call(pending[0]), tool_name=pending[0].name)
                    pending.pop(0)
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

    def __call(self, call: ToolCall, producer: str = "model") -> str:
        """
            Run a tool, asked for by producer ("model", "user" or "system"): whatever goes wrong comes back
            as text, for the model to react
        """
        self.__bus.dispatch(TOOL_CALL_STARTED, name=call.name, arguments=call.arguments, producer=producer)
        log.info(f"[tool] {call.name} {json.dumps(call.arguments, ensure_ascii=False)}")
        start: float = time.perf_counter()
        ok: bool = False
        tool: Tool | None = self.__toolManager.get(call.name)
        if tool is None:
            names: str = ", ".join(schema["function"]["name"] for schema in self.__toolManager.all())
            result = f"Erreur : l'outil '{call.name}' n'existe pas. Les outils disponibles sont : {names}."
        else:
            try:
                result = tool.handle(self, **call.arguments)
                ok = True
            except Exception as e:
                log.exception(f"[tool] {call.name} failed")
                result = (f"Erreur : l'outil '{call.name}' a échoué ({type(e).__name__} : {e}). "
                          "Vérifie tes arguments, ou fais autrement.")
        result = result if isinstance(result, str) else str(result)
        duration: float = time.perf_counter() - start
        log.info(f"[tool] {call.name} done in {duration:.2f}s:\n{result}")
        self.__bus.dispatch(
            TOOL_CALL_ENDED, name=call.name, producer=producer, ok=ok, result=result, duration=round(duration, 3)
        )
        return result
