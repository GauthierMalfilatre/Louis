##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## User def
##

class User:
    def __init__(self, name: str = "Anonymous") -> None:
        """ Initialize a user """
        self.__name: str = name
        self.__role: str = "user"

        self.__history: list[dict[str]] = []

    @property
    def name(self) -> str:
        return self.__name

    @name.setter
    def name(self, name: str) -> None:
        if name and isinstance(name, str):
            self.__name = name

    @property
    def role(self) -> str:
        return self.__role

    @role.setter
    def role(self, role: str) -> None:
        """ Set the role of the user """
        if role and isinstance(role, str):
            self.__role = role

    def stack(self, content: str, *, role: str | None = None) -> list[dict[str]]:
        """ Stack a message onto history and get a list of messages """
        self.__history.append({
            "role"   : self.__role if not role else role,
            "content": content
        })
        return self.__history

    @property
    def history(self) -> list[dict[str]]:
        """ Get history """
        return self.__history
