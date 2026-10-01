##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Permission manager: lets a tool ask the user before it acts
##
from events.event_bus import EventBus
from events.event import Event
from events.event_list import TOOL_BEGFOR_PERMISSION, TOOL_GRANT_PERMISSION

class PermissionManager:
    """ Ask through the bus: TOOL_BEGFOR_PERMISSION asks, TOOL_GRANT_PERMISSION answers with the same id """
    def __init__(self, bus: EventBus):
        """ Init the permission manager """
        self.__bus    : EventBus    = bus
        self.__answer : bool | None = None
        self.__pending: int | None  = None
        self.__last   : int         = 0
        bus.subscribe(self.__on_grant, TOOL_GRANT_PERMISSION)

    def request(self, tool: str, summary: str, preview: str = "", *, every_time: bool = False) -> bool:
        """
            Beg for the permission to run a tool.
            The bus is synchronous: whoever handles the request answers before dispatch returns.
            A request nobody answers is refused, so a missing or broken handler never lets a tool act.
            With several interfaces, the first answer counts: a later one can not overturn it.
            every_time: asked even if the user said "always" to the tools (a link made public, not a file written)
        """
        self.__last += 1
        self.__pending, self.__answer = self.__last, None
        try:
            self.__bus.dispatch(
                TOOL_BEGFOR_PERMISSION, id=self.__last, tool=tool, summary=summary, preview=preview, every_time=every_time
            )
        finally:
            self.__pending = None
        return self.__answer is True

    def __on_grant(self, event: Event) -> None:
        """ Keep the first answer given to the request being asked, the others are ignored """
        if event.data.get("id") == self.__pending and self.__answer is None:
            self.__answer = event.data.get("granted") is True
