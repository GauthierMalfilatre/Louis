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
from model.model import Model, ModelException
from interface.interface import CLI, Interface
from database.database import Database
from session.session import Session
from settings import settings
from tool.tools import ToolRegistry
from tool.sub.tool_gettime import TimenowTool

class AppException(Exception):
    def __init__(self, message: str = "Bad App usage"):
        self.message = message
        super().__init__(self.message)

class App:
    def __init__(self,
            model: str,
            username: str = ANONYMOUS,
            *,
            system_prompt: str = ""
        ):

        if not model:
            raise AppException("You must provide a model name")
        try:
            self.__model  : Model    = Model("http://localhost:11434", model)
        except ModelException:
            raise AppException(f"Unknown model {model}")
        self.__db     : Database | None = None
        if username == ANONYMOUS:
            self.__user: User = User.anonymous()
        else:
            self.__db = Database(settings["db_path"])
            self.__user = User.get_or_create(self.__db, username)
        self.__session: Session | None = self.__user.last_session() if settings["resume"] else None
        if self.__session is None:
            self.__session = self.__user.new_session(system_prompt)

        self.__stream : Interface      = CLI("> ")

        self.__commandTree: CommandTree = CommandTree()\
            .register(PongCommand())\
            .register(ExitCommand())\
            .register(NewSessionCommand())\
            .register(NewModelCommand())

        self.__toolTree: ToolRegistry = ToolRegistry()\
            .register(TimenowTool())

    @property
    def model(self) -> Model:
        return self.__model

    @model.setter
    def model(self, model: str) -> "Model":
        """ Change model """
        self.__model.switch(model)

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
                    userInput: str  = self.__stream.get()
                    if self.__commandTree.fetch(userInput, self):
                        continue

                    self.__stream.out("")

                    response : dict = self.__model.post(
                        self.__session,
                        userInput,
                        role=self.__user.role,
                        tools=self.__toolTree.all(),
                        stream=settings["stream"],
                    )

                    if settings["stream"]:
                        for chunk in response:
                            self.__stream.out(chunk, end="", flush=True)
                        self.__stream.out("\n")
                    else:
                        self.__stream.out(response["message"]["content"] + "\n")

                except (KeyboardInterrupt, EOFError):
                    break
        finally:
            # Always give the terminal back, even on a crash
            self.__stream.close()

        if self.__db is not None:
            self.__db.close()
        self.__stream.out(f"\nGoodbye, {self.__user.name}!\n")
        return self
