##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## App file
##
from user.user import User, ANONYMOUS
from commands.command import CommandTree
from commands.sub.command_pong import PongCommand
from commands.sub.command_exit import ExitCommand
from commands.sub.command_newsession import NewSessionCommand
from commands.sub.command_model import NewModelCommand
from model.model import Model, ModelException, Reply
from interface.interface import CLI, Interface
from database.database import Database
from session.session import Session
from session.message import Message
from settings import settings
from tool.tools import ToolRegistry
from tool.sub.tool_gettime import TimenowTool
from tool.sub.tool_internet import InternetTool
from tool.sub.tool_ls import LSTool
from tool.sub.tool_cd import CDTool
from tool.sub.tool_cat import CatTool
from tool.sub.tool_write import WriteTool

class AppException(Exception):
    def __init__(self, message: str = "Bad App usage"):
        self.message = message
        super().__init__(self.message)

class App:
    def __init__(self,
            model: str,
            username: str = ANONYMOUS,
            *,
            system_prompt: str = "",
            stream: Interface | None = None
        ):

        if not model:
            raise AppException("You must provide a model name")
        try:
            self.__model  : Model    = Model("http://localhost:11434", model)
        except ModelException as e:
            raise AppException(e.message)
        self.__db     : Database | None = None
        if username == ANONYMOUS:
            self.__user: User = User.anonymous()
        else:
            self.__db = Database(settings["db_path"])
            self.__user = User.get_or_create(self.__db, username)
        self.__session: Session | None = self.__user.last_session() if settings["resume"] else None
        if self.__session is None:
            self.__session = self.__user.new_session(system_prompt)

        self.__stream : Interface      = stream if stream is not None else CLI(f"[{self.__user.name}]:{self.__model.model}> ")

        self.__commandTree: CommandTree = CommandTree()\
            .register(PongCommand())\
            .register(ExitCommand())\
            .register(NewSessionCommand())\
            .register(NewModelCommand())

        self.__toolTree: ToolRegistry = ToolRegistry()\
            .register(TimenowTool())\
            .register(InternetTool())\
            .register(LSTool())\
            .register(CatTool())\
            .register(CDTool())\
            # .register(WriteTool())\

        self.__stream.bind(self)

    @property
    def model(self) -> Model:
        return self.__model

    @model.setter
    def model(self, model: str) -> None:
        """ Change model """
        self.__model.switch(newmodel=model)

    @property
    def db(self) -> Database | None:
        return self.__db

    @property
    def user(self) -> User:
        return self.__user

    @property
    def stream(self) -> Interface:
        return self.__stream

    @property
    def session(self) -> Session:
        return self.__session

    @session.setter
    def session(self, session: Session) -> "App":
        if isinstance(session, Session):
            self.__session = session

    @property
    def commandTree(self) -> CommandTree:
        return self.__commandTree

    def run(self) -> "App":
        try:
            while self.__stream.isOpen():
                try:
                    userInput: str = self.__stream.get()
                    if not userInput.strip() or self.__commandTree.fetch(userInput, self):
                        continue

                    self.__stream.out("")
                    self.__turn(userInput)
                except ModelException as e:
                    self.__stream.out(f"\n{e.message}\n")
                except (KeyboardInterrupt, EOFError):
                    break
        finally:
            self.__stream.close()

        if self.__db is not None:
            self.__db.close()
        self.__stream.out(f"\nGoodbye, {self.__user.name}!\n")
        return self

    def __turn(self, text: str) -> None:
        """ Answer a user message, running the tools the model asks for """
        # Saved only once complete: a failure or Ctrl+C leaves no half-turn in the session
        pending: list[Message] = [Message("user", text)]

        for _ in range(settings["max_tool_rounds"]):
            reply: Reply = self.__model.chat(
                self.__session.history + [message.to_dict() for message in pending],
                self.__toolTree.all(),
                on_text=self.__print_chunk if settings["stream"] else None,
            )
            if reply.content:
                if not settings["stream"]:
                    self.__stream.out(reply.content, end="")
                self.__stream.out("\n")

            pending.append(Message("assistant", reply.content, tool_calls=reply.tool_calls or None))
            if not reply.tool_calls:
                break
            for call in reply.tool_calls:
                pending.append(Message("tool", self.__toolTree.call(call, self), tool_name=call.name))
        else:
            self.__stream.out(f"Stopped after {settings['max_tool_rounds']} rounds of tool calls.\n")

        for message in pending:
            self.__session.stack(
                message.content,
                role=message.role,
                tool_calls=message.tool_calls,
                tool_name=message.tool_name
            )

    def __print_chunk(self, chunk: str) -> None:
        self.__stream.out(chunk, end="", flush=True)
