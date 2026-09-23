##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Event bus: lets an interface (or anything else) react to what happens in the app
## without App having to know who is listening
##
from collections.abc import Callable
from dataclasses import dataclass, field

# One name per thing worth reacting to. Add here, not ad hoc strings elsewhere.
MODEL_SWITCHED : str = "model.switched"   # data: previous, current
SESSION_OPENED : str = "session.opened"   # data: id (a fresh or a switched-to session)
TOOL_START     : str = "tool.start"       # data: name, arguments
TOOL_END       : str = "tool.end"         # data: name, ok, result

@dataclass(frozen=True, slots=True)
class Event:
    name: str
    data: dict = field(default_factory=dict)

class EventBus:
    def __init__(self) -> None:
        self.__handlers: list[tuple[Callable[[Event], None], frozenset[str]]] = []

    def subscribe(self, handler: Callable[[Event], None], *names: str) -> "EventBus":
        """ Register a handler, for every event or only the given names """
        self.__handlers.append((handler, frozenset(names)))
        return self

    def dispatch(self, name: str, /, **data) -> None:
        """ Notify every handler that cares about this event.
            name is positional-only: an event's own data may legitimately need a "name"
            field too (e.g. TOOL_START's tool name), and must not collide with this one.
        """
        event: Event = Event(name, data)
        for handler, names in self.__handlers:
            if names and name not in names:
                continue
            try:
                handler(event)
            except Exception:
                pass  # A broken subscriber must never break a turn
