##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Event bus
##
from .event import Event
from collections.abc import Callable
from logger.logger import log

class EventBus:
    """ Event bus class """
    def __init__(self):
        self.__handlers: list[tuple[Callable[[Event], None], frozenset[str]]] = []

    def subscribe(self, handler: Callable[[Event], None], *names: str) -> "EventBus":
        """ Register a handler, for every event or only the given names """
        self.__handlers.append((handler, frozenset(names)))
        return self

    def dispatch(self, name: str, /, **data) -> None:
        """
            Notify every handler that cares about this event.
            name is positional-only: an event's own data may legitimately need a "name"
            field too (e.g. TOOL_START's tool name), and must not collide with this one.
        """
        event: Event = Event(name, data)
        for handler, names in self.__handlers:
            if names and name not in names:
                continue
            # A broken handler must not break the others, nor the turn: it is only logged
            try:
                handler(event)
            except Exception:
                log.exception(f"[event] a handler of {name} failed")
