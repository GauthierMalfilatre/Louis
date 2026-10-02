##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tool class
##
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class ToolCall:
    name     : str
    arguments: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "ToolCall":
        """ Parse a tool call from the model API format """
        function: dict = data.get("function") or {}
        return cls(function.get("name", ""), function.get("arguments") or {})

    def to_dict(self) -> dict:
        """ Format for the model API """
        return {"function": {"name": self.name, "arguments": self.arguments}}
