##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## ToolManager class
##
from .tool import Tool

class ToolManager:
    """ Tool manager, to manage tooling """
    def __init__(self):
        """ Init the tool manager """
        self.__tools: dict = {}

    def register(self, tool: Tool) -> "ToolManager":
        """ Register a tool to the manager """
        self.__tools[tool.name] = tool
        return self

    def has(self, name: str) -> bool:
        """ Wether the manager has the tool """
        return name in self.__tools.keys()

    def get(self, name: str) -> bool | None:
        """ Get the tool requested """
        return self.__tools.get(name)

    def all(self) -> list[dict]:
        """ Get all the tools """
        return [self.__tools[t].schema for t in self.__tools.keys()]
