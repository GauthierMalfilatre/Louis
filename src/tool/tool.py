##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tool class
##
from abc import abstractmethod

# How the result of a tool starts when it could not do what was asked: it can not, or the user refused
FAILURES: tuple[str, ...] = ("Erreur", "Refusé")

def failed(result: str) -> bool:
    """ Whether the result of a tool tells that it could not do what was asked """
    return result.lstrip().startswith(FAILURES)

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
