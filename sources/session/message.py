##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Message file
##
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True, slots=True)
class Message:
    role      : str
    content   : str
    id        : int | None      = None
    session_id: int | None      = None
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, str]:
        """ Format for the model API """
        return {"role": self.role, "content": self.content}
