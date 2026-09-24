##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Command and CommandTree classes: the /commands typed by the user
##
from logger.logger import log
import re

# Only a plain word can name a command: "/src/main.py, que fait ce fichier ?" is a message
WORD: re.Pattern = re.compile(r"[A-Za-z][\w-]*")

class Command:
    """ A /command, run by Louis itself instead of being sent to the model """
    def __init__(self, name: str, *, alias: list[str] | None = None, description: str = "", usage: str = ""):
        """ Init a command, usage describes its arguments (e.g. "<id>") """
        self.__name       : str       = name
        self.__alias      : list[str] = alias or []
        self.__description: str       = description
        self.__usage      : str       = usage

    @property
    def name(self) -> str:
        """ Get the name of the command, typed after the prefix """
        return self.__name

    @property
    def alias(self) -> list[str]:
        """ Get the other names of the command """
        return self.__alias

    @property
    def description(self) -> str:
        """ Get what the command does """
        return self.__description

    @property
    def usage(self) -> str:
        """ Get the arguments of the command """
        return self.__usage

    def match(self, keyword: str) -> bool:
        """ Whether the command is named keyword """
        return keyword == self.__name or keyword in self.__alias

    def handle(self, app, arguments: str) -> None:
        """ Run the command, with everything typed after its name """
        raise NotImplementedError

class CommandTree:
    """ The commands Louis knows: a message that starts with one runs it """
    def __init__(self, prefix: str = "/"):
        """ Init an empty command tree """
        self.__prefix  : str           = prefix
        self.__commands: list[Command] = []

    @property
    def commands(self) -> list[Command]:
        """ Get the registered commands """
        return list(self.__commands)

    def register(self, command: Command) -> "CommandTree":
        """ Register a command, under a name no other command has """
        for name in (command.name, *command.alias):
            if any(known.match(name) for known in self.__commands):
                raise ValueError(f"The command {self.__prefix}{name} is already registered")
        self.__commands.append(command)
        return self

    def help(self) -> str:
        """ Get the list of the commands, with their arguments and what they do """
        return "\n".join(
            f"  {f'{self.__prefix}{command.name} {command.usage}'.strip():18} {command.description}"
            for command in self.__commands
        )

    def fetch(self, content: str, app) -> bool:
        """ Run the command a message starts with, and tell whether it was one """
        words: list[str] = content.strip().split(maxsplit=1)
        if not words or not words[0].startswith(self.__prefix):
            return False
        keyword: str = words[0].removeprefix(self.__prefix)
        if not WORD.fullmatch(keyword):
            return False
        # Everything after the command word, spaces and newlines kept
        arguments: str = words[1] if len(words) > 1 else ""

        command: Command | None = next((command for command in self.__commands if command.match(keyword)), None)
        if command is None:
            app.stream.out(f"\nCommande inconnue : {self.__prefix}{keyword}. Les commandes sont :\n{self.help()}\n")
            return True
        log.info(f"[command] {self.__prefix}{keyword} {arguments}".rstrip())
        command.handle(app, arguments)
        return True
