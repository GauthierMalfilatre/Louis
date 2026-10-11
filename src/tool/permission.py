##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Permission manager: lets a tool ask the user before it acts
##
from events.event_bus import EventBus
from events.event import Event
from events.event_list import TOOL_BEGFOR_PERMISSION, TOOL_GRANT_PERMISSION, PLAN_PROPOSED, PLAN_DECIDED

class PermissionManager:
    """ Ask through the bus: TOOL_BEGFOR_PERMISSION asks, TOOL_GRANT_PERMISSION answers with the same id """
    def __init__(self, bus: EventBus):
        """ Init the permission manager """
        self.__bus    : EventBus    = bus
        self.__answer : bool | None = None
        self.__pending: int | None  = None
        self.__last   : int         = 0
        # True while a call that can not be undone runs (a push, a merge): the app sets it, then sets it back.
        # Whatever the call asks is then asked every time, never granted by an "always" given to its tool
        self.strict   : bool        = False
        # True while a call of a plan the user approved runs: what it asks is granted at once, the user said yes to
        # the whole plan, its diffs in it. The app sets it, then sets it back
        self.granted  : bool        = False
        # The plan being asked (its id), and the answer: approved, and what the user said
        self.__plan   : int | None  = None
        self.__decision: tuple[bool, str] | None = None
        bus.subscribe(self.__on_grant, TOOL_GRANT_PERMISSION)
        bus.subscribe(self.__on_decided, PLAN_DECIDED)

    def request(self, tool: str, summary: str, preview: str = "", *, every_time: bool = False) -> bool:
        """
            Beg for the permission to run a tool.
            The bus is synchronous: whoever handles the request answers before dispatch returns.
            A request nobody answers is refused, so a missing or broken handler never lets a tool act.
            With several interfaces, the first answer counts: a later one can not overturn it.
            every_time: asked even if the user said "always" to the tools (a link made public, not a file written),
            as every request while strict is True. While granted is True, granted without asking
        """
        if self.granted:
            return True
        every_time = every_time or self.strict
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

    def propose(self, intent: str, actions: list[dict]) -> tuple[bool, str]:
        """
            Show the user the plan of a reply before any of its calls runs: what the model meant, and each call with
            what it would do (PLAN_PROPOSED). Whether they approved it, and what they said instead ("" if nothing).
            As a request, it waits for the answer on the bus, the first one counts, and nobody answering is a no
        """
        self.__last += 1
        self.__plan, self.__decision = self.__last, None
        try:
            self.__bus.dispatch(PLAN_PROPOSED, id=self.__last, intent=intent, actions=actions)
        finally:
            self.__plan = None
        return self.__decision or (False, "")

    def __on_decided(self, event: Event) -> None:
        """ Keep the first answer given to the plan being asked, the others are ignored """
        if event.data.get("id") == self.__plan and self.__decision is None:
            feedback = event.data.get("feedback")
            self.__decision = (event.data.get("approved") is True, feedback.strip() if isinstance(feedback, str) else "")
