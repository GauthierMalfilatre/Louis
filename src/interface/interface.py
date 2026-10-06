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
    # What the scribe (session/scribe.py) writes for this interface: the titles and summaries of the sessions, and the
    # sentence that welcomes the user to a new one. A script that asks one question and quits needs none of it
    describes: bool = True
    welcomes : bool = False

    def __init__(self) -> "Interface":
        """ Init the class Interface """
        ...

    def __enter__(self) -> "Interface":
        """ Open the interface (a window, a server...): nothing to do by default """
        return self

    def __exit__(self, *exception) -> None:
        """ Close it, even when Louis crashes: the terminal must be left as it was found """
        return None

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
