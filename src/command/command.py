##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Command and CommandTree classes: the /commands typed by the user
##
from logger.logger import log
from events.event_list import COMMAND_UNKNOWN, COMMAND_ERROR
import re

# Only a plain word can name a command: "/src/main.py, que fait ce fichier ?" is a message. The prompts of the MCP
# servers are named <server>:<prompt>
WORD: re.Pattern = re.compile(r"[A-Za-z][\w-]*(?::[\w-]+)?")

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

    def describe(self) -> dict:
        """ Get what an interface needs to present the command """
        return {"name": self.__name, "usage": self.__usage, "description": self.__description}

    def error(self, app, reason: str, message: str, **details) -> None:
        """ Tell the interfaces the command failed: reason is a short code, message one plain sentence """
        app.events.dispatch(COMMAND_ERROR, command=self.__name, reason=reason, message=message, **details)

    def handle(self, app, arguments: str) -> None:
        """ Run the command, with everything typed after its name: what it has to show goes through events """
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

    def unregister(self, name: str) -> "CommandTree":
        """ Withdraw the command of that name, if there is one """
        self.__commands = [command for command in self.__commands if command.name != name]
        return self

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
            app.events.dispatch(COMMAND_UNKNOWN, name=keyword, commands=[known.describe() for known in self.__commands])
            return True
        log.info(f"[command] {self.__prefix}{keyword} {arguments}".rstrip())
        # A broken command must not stop Louis: the user is told, the traceback goes to the log
        try:
            command.handle(app, arguments)
        except Exception as e:
            log.exception(f"[command] {self.__prefix}{keyword} failed")
            command.error(app, "failed", f"La commande {self.__prefix}{keyword} a échoué : {e}")
        return True
