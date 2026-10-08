##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Quiet interface: one question asked by a script, nothing shown but the errors, on stderr
##
from interface.interface import Interface
from events.event_bus import EventBus
from events.event import Event
from events.event_list import CHAT_TURN_ENDED, COMMAND_ERROR
import sys

class QuietInterface(Interface):
    """
        For louis --ask: stdout is only the reply, for a script to read. What went wrong goes to stderr, and the
        permissions are never asked (nobody answers: a tool never acts)
    """
    # One question, then Louis quits: the scribe would load its model for nothing
    describes: bool = False

    def bind(self, bus: EventBus) -> "QuietInterface":
        """ Only the errors: why a turn gave no answer, why a command failed """
        bus.subscribe(self.__on_turn_ended, CHAT_TURN_ENDED)
        bus.subscribe(lambda event: self.__error(event.data["message"]), COMMAND_ERROR)
        return self

    def getUserInput(self) -> str:
        """ No message of the user: the question is given when louis starts """
        raise EOFError

    def __on_turn_ended(self, event: Event) -> None:
        """ A turn that gave no answer, and why """
        if event.data["reason"] != "done":
            self.__error(event.data.get("message") or f"Pas de réponse ({event.data['reason']}).")

    @staticmethod
    def __error(message: str) -> None:
        """ One line on stderr: stdout stays the reply alone """
        sys.stderr.write(f"louis : {message}\n")
        sys.stderr.flush()
