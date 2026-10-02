##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Message file
##
from dataclasses import dataclass
from datetime import datetime
from bootstrap.sources.tool.tools import ToolCall

@dataclass(frozen=True, slots=True)
class Message:
    role      : str
    content   : str
    id        : int | None            = None
    session_id: int | None            = None
    created_at: datetime | None       = None
    tool_calls: list[ToolCall] | None = None
    tool_name : str | None            = None
    images    : list[str] | None      = None  # Base64, as the model API wants them

    def to_dict(self) -> dict:
        """ Format for the model API """
        message: dict = {"role": self.role, "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [call.to_dict() for call in self.tool_calls]
        if self.tool_name:
            message["tool_name"] = self.tool_name
        if self.images:
            message["images"] = self.images
        return message
