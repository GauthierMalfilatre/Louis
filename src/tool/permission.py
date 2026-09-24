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
        self.__bus    : EventBus        = bus
        self.__answers: dict[int, bool] = {}
        self.__last   : int             = 0
        bus.subscribe(self.__on_grant, TOOL_GRANT_PERMISSION)

    def request(self, tool: str, summary: str, preview: str = "") -> bool:
        """
            Beg for the permission to run a tool.
            The bus is synchronous: whoever handles the request answers before dispatch returns.
            A request nobody answers is refused, so a missing or broken handler never lets a tool act.
        """
        self.__last += 1
        request_id: int = self.__last
        self.__bus.dispatch(TOOL_BEGFOR_PERMISSION, id=request_id, tool=tool, summary=summary, preview=preview)
        return self.__answers.pop(request_id, False)

    def __on_grant(self, event: Event) -> None:
        """ Keep the answer given to a request """
        self.__answers[event.data.get("id")] = event.data.get("granted") is True
