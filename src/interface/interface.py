##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Abstract class Interface to implemente CLI or Web Interface
##
from abc import ABC, abstractmethod

class Interface(ABC):
    """ Abstract Base Class Interface """
    def __init__(self) -> "Interface":
        """ Init the class Interface """
        ...

    def bind(self, bus) -> "Interface":
        """
            Subscribe to the events of the bus this interface shows, laid out its own way:
            SESSION_LIST as text for the CLI, as a table for a web page... None by default
        """
        return self

    @abstractmethod
    def getUserInput(self) -> str:
        """ Get the user input, raise EOFError when there is no more of it """
        ...

    @abstractmethod
    def ask(self, question: str) -> str:
        """ Ask the user a question, and get the answer """
        ...

    @abstractmethod
    def out(self, content: str, *, end="\n", flush=False) -> "Interface":
        """ Print out on the interface """
        ...

    @abstractmethod
    def debug(self, content: str) -> "Interface":
        """ Print something on the debug channel """
        ...
