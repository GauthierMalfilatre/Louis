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
from model.model import Model
from interface.interface import CLI, Interface
from database.database import Database
from session.session import Session
from settings import settings

class App:
    def __init__(self,
            username: str = ANONYMOUS,
            *,
            system_prompt: str = ""
        ):
        self.__model  : Model    = Model("http://localhost:11434/api/chat", "qwen2.5-coder:7b")
        self.__db     : Database | None = None
        if username == ANONYMOUS:
            # Anonymous leaves no trace: the database is not even opened
            self.__user: User = User.anonymous()
        else:
            self.__db = Database(settings["db_path"])
            self.__user = User.get_or_create(self.__db, username)
        self.__stream : Interface      = CLI(f"({self.__user.name})$ ")
        self.__session: Session | None = self.__user.last_session() if settings["resume"] else None
        if self.__session is None:
            self.__session = self.__user.new_session(system_prompt)

        self.__commandTree: CommandTree = CommandTree()\
            .register(PongCommand())\
            .register(ExitCommand())

    @property
    def model(self) -> Model:
        return self.__model

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

    @property
    def commandTree(self) -> CommandTree:
        return self.__commandTree

    def run(self) -> "App":
        while self.__stream.isOpen():
            try:
                userInput: str  = self.__stream.get()
                if self.__commandTree.fetch(userInput, self):
                    continue

                self.__stream.out("")

                response : dict = self.__model.post(
                    self.__session, userInput,
                    role=self.__user.role,
                    stream=settings["stream"]
                )

                if settings["stream"]:
                    for chunk in response:
                        self.__stream.out(chunk, end="", flush=True)
                    self.__stream.out("\n")
                else:
                    self.__stream.out(response["message"]["content"] + "\n")

            except KeyboardInterrupt:
                break

        if self.__db is not None:
            self.__db.close()
        self.__stream.out(f"Goodbye, {self.__user.name}!")
        return self
