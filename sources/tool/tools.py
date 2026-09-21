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
        ...

class ToolRegistryException(Exception):
    def __init__(self, message: str = "Bad Tool Registry Usage"):
        self.message = message
        super().__init__(self.message)

class ToolRegistry:
    def __init__(self) -> "ToolRegistry":
        self.__tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> "ToolRegistry":
        """ Register a new tool """
        self.__tools[tool.schema["function"]["name"]] = tool
        return self

    def fetch(self, key: str, manager) -> str:
        """ Fetch """
        tool: Tool | None = self.__tools.get(key)
        if tool is None:
            raise ToolRegistryException(f"Cannot use tool {key}")
        return tool.handler(manager)

    def all(self) -> list[dict[str]]:
        return [self.__tools[key].schema for key in self.__tools.keys()]
