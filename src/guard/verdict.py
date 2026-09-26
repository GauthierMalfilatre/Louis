##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Verdict of the guard on a message
##
from dataclasses import dataclass, field

PASS   : str = "pass"      # the message goes through untouched
MASKED : str = "masked"    # the message goes through, its sensitive data replaced
REFUSED: str = "refused"   # the message is replaced by a refusal

@dataclass
class Verdict:
    action : str
    # What goes on in place of the message: itself, masked, or the refusal
    content: str
    # The rails that refused it, by their flow name
    rails  : list[str] = field(default_factory=list)

    @property
    def refused(self) -> bool:
        """ Check if the message must not go on """
        return self.action == REFUSED
