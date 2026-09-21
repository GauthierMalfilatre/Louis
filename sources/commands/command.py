##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Command file
##

class Command:
    def __init__(self, name: str, *, alias: list[str] = []) -> "Command":
        """ Init a command """
        self.__name   = name
        self.__alias  = alias

    def match(self, keyword: str) -> bool:
        """ Check if command match a keyword """
        return (keyword == self.__name) or (keyword in self.__alias)

    def handler(self, content: str) -> bool:
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

    def fetch(self, content: str) -> bool:
        """ Check if is a command and then execute it """
        keyword: str = content.split()
        if not keyword or len(keyword) < 1:
            raise CommandTreeException(f"Bad message {content}")
        keyword = keyword[0]
        if not keyword.startswith(self.__prefix):
            return False
        keyword = keyword.removeprefix(self.__prefix)
        for cmd in self.__commands:
            if cmd.match(keyword):
                return cmd.handler(keyword)
        return False

    def register(self, command: Command) -> "CommandTree":
        if not isinstance(command, Command):
            raise CommandTreeException("Bad command")
        # TODO: Check if command is not already registered
        self.__commands.append(command)
        return self
