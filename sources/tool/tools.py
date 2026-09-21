##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tools file
##


class Tool:
    def __init__(self,
            name: str,
            description: str,
            parameters: dict
        ) -> "Tool":
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
    def schema(self) -> dict:
        return self.__schema

    def handler(self, manager) -> str:
        """ Handler """
        return ""

class ToolRegistryException(Exception):
    def __init__(self, message: str = "Bad Tool Registry Usage"):
        self.message = message
        super().__init__(self.message)

class ToolRegistry:
    def __init__(self) -> "ToolRegistry":
        self.__tools: dict[str, Tool] = []

    def register(self, tool: Tool) -> "ToolRegistry":
        """ Register a new tool """
        self.__tools[tool.name] = tool

    def fetch(self, key: str, manager) -> str:
        """ Fetch """
        tool: Tool | None = self.__tools.get(key)
        if tool is None:
            raise ToolRegistryException(f"Cannot use tool {key}")
        tool.handler(manager)
