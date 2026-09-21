##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## User def
##

class User:
    def __init__(self, name: str) -> None:
        """ Initialize a user """
        self.__name: str = name
        self.__role: str = "user"

    @property
    def name(self) -> str:
        return self.__name

    @property.setter
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
