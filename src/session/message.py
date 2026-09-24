##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Message class
##
from dataclasses import dataclass
from tool.tool_call import ToolCall
import json
import sqlite3

@dataclass
class Message:
    """ One message of a session: from the system, the user, the model, or a tool """
    role      : str
    content   : str
    tool_calls: list[ToolCall] | None = None
    tool_name : str | None            = None
    id        : int | None            = None
    created_at: str | None            = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Message":
        """ Rebuild a message saved in the database """
        calls: str | None = row["tool_calls"]
        return cls(
            row["role"],
            row["content"],
            [ToolCall.from_dict(call) for call in json.loads(calls)] if calls else None,
            row["tool_name"],
            row["id"],
            row["created_at"]
        )

    def calls_json(self) -> str | None:
        """ The tool calls, as they are saved in the database """
        if not self.tool_calls:
            return None
        return json.dumps([call.to_dict() for call in self.tool_calls], ensure_ascii=False)

    def to_dict(self) -> dict:
        """ The message in the format of the model API """
        message: dict = {"role": self.role, "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [call.to_dict() for call in self.tool_calls]
        if self.tool_name:
            message["tool_name"] = self.tool_name
        return message
