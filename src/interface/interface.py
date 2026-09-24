##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Abstract class Interface to implemente CLI or Web Interface
##
from abc import ABC, abstractmethod

class Interface(ABC):
    """
        What the user talks to Louis through: it gives the messages of the user, and shows what happens by
        listening to the events of the app (the conversation, the commands, the permissions to ask...)
    """
    def __init__(self) -> "Interface":
        """ Init the class Interface """
        ...

    @abstractmethod
    def bind(self, bus) -> "Interface":
        """
            Subscribe to the events of the bus this interface shows, laid out its own way:
            SESSION_LIST as text for the CLI, as a table for a web page...
            The permissions are answered here too: TOOL_BEGFOR_PERMISSION asks, TOOL_GRANT_PERMISSION answers
        """
        ...

    @abstractmethod
    def getUserInput(self) -> str:
        """ Wait for the next message of the user, raise EOFError when there is no more of them """
        ...
