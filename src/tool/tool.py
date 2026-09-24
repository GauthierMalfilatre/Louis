##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tool class
##
from abc import abstractmethod

class Tool:
    """ Class tool """
    def __init__(self, name: str, desc: str, parameters: dict = {}) -> "Tool":
        """ Init a tool """
        self.__schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": parameters
            }
        }

    @property
    def name(self) -> str:
        """ Get the name of the tool """
        return self.__schema["function"]["name"]

    @property
    def desc(self) -> str:
        """ Get the description of the tool """
        return self.__schema["function"]["description"]

    @property
    def schema(self) -> dict[str]:
        """ Get the schema of the tool """
        return self.__schema

    @abstractmethod
    def handle(self, app, **kwargs):
        """ The handler of the tool class """
        ...
