##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Command file
##
class Command:
    def __init__(self,
            name: str,
            *,
            alias: list[str] = [],
            description: str = "",
            usage: str = ""
        ) -> "Command":
        """ Init a command, usage describes its arguments (e.g. "<name>") """
        self.__name        = name
        self.__alias       = alias
        self.__description = description
        self.__usage       = usage

    @property
    def name(self) -> str:
        return self.__name

    @property
    def alias(self) -> list[str]:
        return self.__alias

    @property
    def description(self) -> str:
        return self.__description

    @property
    def usage(self) -> str:
        return self.__usage

    def match(self, keyword: str) -> bool:
        """ Check if command match a keyword """
        return (keyword == self.__name) or (keyword in self.__alias)

    def handler(self, content: str, manager) -> bool:
        """ Handler to override """
        return True

class CommandTreeException(Exception):
    def __init__(self, message: str = "Bad CommandTree usage"):
        self.message = message
        super().__init__(self.message)

class CommandTree:
    def __init__(self, *, prefix: str = "/") -> "CommandTree":
        """ Init a command tree """
        self.__prefix  : str           = prefix
        self.__commands: list[Command] = []

    @property
    def prefix(self) -> str:
        return self.__prefix

    @property
    def commands(self) -> list[Command]:
        """ Get the registered commands """
        return list(self.__commands)

    def fetch(self, content: str, manager) -> bool:
        """ Check if is a command and then execute it """
        keyword_: str = content.split()
        if not keyword_ or len(keyword_) < 1:
            raise CommandTreeException(f"Bad message {content}")
        keyword = keyword_[0]
        if not keyword.startswith(self.__prefix):
            return False
        keyword = keyword.removeprefix(self.__prefix)
        for cmd in self.__commands:
            if cmd.match(keyword):
                return cmd.handler("".join(keyword_[1:]), manager)
        return False

    def register(self, command: Command) -> "CommandTree":
        if not isinstance(command, Command):
            raise CommandTreeException("Bad command")
        # TODO: Check if command is not already registered
        self.__commands.append(command)
        return self
