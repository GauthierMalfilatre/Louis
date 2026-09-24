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

    @abstractmethod
    def getUserInput(self) -> str:
        """ Get the user input """
        ...

    @abstractmethod
    def out(self, content: str) -> "Interface":
        """ Print out on the interface """
        ...

    @abstractmethod
    def debug(self, content: str) -> "Interface":
        """ Print something on the debug channel """
        ...
