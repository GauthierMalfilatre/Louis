##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tool class
##
from abc import abstractmethod
from tool.risk import Risk, NONE

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

    def describe(self, desc: str) -> None:
        """ Change the description of the tool, when what it can reach changed (what the knowledge base holds) """
        self.__schema["function"]["description"] = desc

    def risk(self, app, **kwargs) -> Risk:
        """
            What the call would do, judged before it runs, without running it: the app suspends the calls risky
            enough to show their plan first. A tool that only reads changes nothing. A call it can not judge (wrong
            arguments) is safe: the tool refuses it itself
        """
        return NONE

    @abstractmethod
    def handle(self, app, **kwargs):
        """ The handler of the tool class """
        ...
