##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tools file
##
from dataclasses import dataclass, field
import json
from events.events import TOOL_START, TOOL_END

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

class Tool:
    def __init__(self,
            name: str,
            description: str,
            parameters: dict
        ) -> None:
        """ Init a tool """
        self.__schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters
            }
        }

    @property
    def name(self) -> str:
        return self.__schema["function"]["name"]

    @property
    def schema(self) -> dict:
        return self.__schema

    def handler(self, manager, **kwargs) -> str:
        """ Run the tool with the arguments chosen by the model """
        raise NotImplementedError

class ToolRegistry:
    def __init__(self) -> None:
        self.__tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> "ToolRegistry":
        """ Register a new tool """
        self.__tools[tool.name] = tool
        return self

    def call(self, call: ToolCall, manager) -> str:
        """ Run a tool call, failures are returned as text so the model can react to them """
        tool: Tool | None = self.__tools.get(call.name)
        if tool is None:
            return f"Error: unknown tool '{call.name}'"

        manager.events.dispatch(TOOL_START, name=call.name, arguments=call.arguments)
        try:
            result = tool.handler(manager, **call.arguments)
            ok: bool = True
        except Exception as e:
            result, ok = f"Error: tool '{call.name}' failed: {e}", False
        result = result if isinstance(result, str) else json.dumps(result, default=str)
        manager.events.dispatch(TOOL_END, name=call.name, ok=ok, result=result)
        return result

    def all(self) -> list[dict]:
        """ Get every tool schema, for the model API """
        return [tool.schema for tool in self.__tools.values()]
