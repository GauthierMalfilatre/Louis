##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Actions of the rails: the code the flows of rails.co call with "execute", loaded by NeMo itself.
## They only read a text and answer: no bus, no interface, no log of Louis (they run in the loop of NeMo)
##
from nemoguardrails.actions import action
from guard import patterns

# async: NeMo runs them in its event loop, and warns about the synchronous ones
@action(name="mask_french_ids")
async def mask_french_ids(text: str) -> str:
    """ The text, its French ids replaced by their kind """
    return patterns.mask_french_ids(text)

@action(name="contains_secret")
async def contains_secret(text: str) -> bool:
    """ Check if the text holds a secret """
    return patterns.contains_secret(text)

@action(name="tool_call_leaks")
async def tool_call_leaks(calls: list[dict] | None = None, config=None) -> bool:
    """ Check if a call to a tool of custom_data.guard.outbound_tools has sensitive data in its arguments """
    outbound: list[str] = ((config.custom_data if config else {}).get("guard") or {}).get("outbound_tools") or []
    for call in calls or []:
        function: dict = call.get("function") or {}
        if function.get("name") not in outbound:
            continue
        # What the log would mask would leave the machine
        if any(patterns.redact(str(value)) != str(value) for value in (function.get("arguments") or {}).values()):
            return True
    return False
