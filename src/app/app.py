##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## App Class (the manager)
##

from interface.interface import Interface
from interface.cli import CLI
from model.model import OllamaModel
from model.reply import Reply
from tool.tool_manager import ToolManager
from tool.tool import Tool
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

class App:
    """ App Class """
    def __init__(self, settings: dict[str], system_prompt: str, user: User):
        """ Init the Application class, on a new session of the user """
        self.__settings: dict[str] = settings
        self.__user: User = user
        self.__system_prompt: str = system_prompt

        self.__bus: EventBus = EventBus()
        # Subscribed first: an event is logged before any other handler reacts to it
        self.__bus.subscribe(log_event)

        self.__permissions: PermissionManager = PermissionManager(self.__bus)
        self.__bus.subscribe(self.__ask_permission, TOOL_BEGFOR_PERMISSION)

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

        # NOTE: Raisable
        self.__model : OllamaModel = OllamaModel(settings["chat.uri"], f"{settings["chat.model.name"]}:{settings["chat.model.parameters"]}")

        self.__stream: Interface   = CLI("> ")

        # Started once the model answers: a failed start leaves no empty session behind
        self.new_session()

    @property
    def stream(self) -> Interface:
        """ Get the current stream (interface) """
        return self.__stream

    @property
    def user(self) -> User:
        """ Get the user talking to Louis """
        return self.__user

    @property
    def session(self) -> Session:
        """ Get the current session of the user, where the conversation is kept """
        return self.__user.current_session

    def new_session(self, system_prompt: str | None = None) -> Session:
        """ Start a new session of the user, on the given system prompt or on the one Louis started with """
        session: Session = self.__user.new_session(os.getcwd())
        session.add("system", system_prompt or self.__system_prompt)
        log.info(f"[session] {'new session' if self.__user.is_anonymous else f'#{session.id}'} of {self.__user.name}"
                 f"{' (not saved)' if self.__user.is_anonymous else ''}")
        return session

    @property
    def permissions(self) -> PermissionManager:
        """ Get the permission manager, for the tools to ask before acting """
        return self.__permissions

    def run(self):
        """ Run the application """

        while True:
            try:
                u = self.stream.getUserInput()
                if not u.strip():
                    continue
                log.info(f"[user] {u.strip()}")
                if self.__commands.fetch(u, self):
                    continue

                self.session.add("user", u)

                self.stream.out("\n", end="")

                nudged: bool = False
                for _ in range(self.__settings.get("chat.tools.maxdepth", 8)):
                    reply: Reply = self.__model.chat(
                        self.session.history,
                        self.__toolManager.all(),
                        on_text=self.__print_chunck
                    )

                    self.session.add("assistant", reply.content, tool_calls=reply.tool_calls)

                    if not reply.tool_calls:
                        # Once per message, so a wrong guess costs one round and never loops
                        if nudged or not ANNOUNCE.search(reply.content):
                            break
                        nudged = True
                        log.info("[app] the model announced an action without calling a tool: nudging it")
                        self.stream.debug("\n(Louis a annoncé une action sans la faire : relance)\n")
                        self.session.add("user", NUDGE_PROMPT)
                        continue

                    self.__bus.dispatch(TOOL_USAGE_STARTED)
                    for call in reply.tool_calls:
                        tool: Tool = self.__toolManager.get(call.name)
                        self.stream.debug(f"Calling tool {call.name}\n")
                        log.info(f"[tool] {call.name} {json.dumps(call.arguments, ensure_ascii=False)}")
                        start: float = time.perf_counter()
                        resp = tool.handle(self, **call.arguments)
                        log.info(f"[tool] {call.name} done in {time.perf_counter() - start:.2f}s:\n{resp}")

                        self.session.add("tool", resp, tool_name=call.name)
                    self.__bus.dispatch(TOOL_USAGE_ENDED)

                else:
                    log.warning(f"[app] stopped after {self.__settings.get("chat.tools.maxdepth", 8)} rounds of tool calls")
                    self.stream.debug(f"Stopped after {self.__settings.get("chat.tools.maxdepth", 8)} round of tool calls\n")

                self.stream.out("\n")

            except (KeyboardInterrupt, EOFError) as e:
                log.info(f"[app] session closed by the user ({type(e).__name__})")
                self.stream.debug("\nUser has closed the session...\n")
                break
        return 0

    def __ask_permission(self, event: Event) -> None:
        """ Show the user what a tool wants to do, and grant it if they agree """
        self.stream.out(f"\n{event.data['summary']}")
        if event.data.get("preview"):
            self.stream.out(event.data["preview"])
        answer: str = self.stream.ask("Autoriser ? [y/n] ")
        self.__bus.dispatch(
            TOOL_GRANT_PERMISSION,
            id=event.data["id"],
            granted=answer.strip().lower() in ("o", "oui", "y", "yes")
        )

    def __print_chunck(self, text) -> None:
        """ Print a chunck """
        self.stream.out(text, end="", flush=True)
