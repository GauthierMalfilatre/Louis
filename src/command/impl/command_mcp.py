##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /mcp: the MCP servers of the settings, their state and their tools
##
from command.command import Command
from events.event_list import MCP_SERVERS

class McpCommand(Command):
    def __init__(self):
        super().__init__("mcp", description="liste les serveurs MCP, leur état et leurs outils")

    def handle(self, app, arguments: str) -> None:
        """ Send every server of the settings, started or not, with its state and its tools """
        app.events.dispatch(MCP_SERVERS, servers=app.mcp.describe())
