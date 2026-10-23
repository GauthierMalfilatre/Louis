##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /mcp: the MCP servers of the settings, their state and their tools; /mcp restart|stop <server> to manage one
##
from command.command import Command
from events.event_list import MCP_SERVERS

# What /mcp does to a server, by the word typed after it, and the change the user is told
ACTIONS: dict[str, str] = {"restart": "restarted", "stop": "stopped"}

class McpCommand(Command):
    def __init__(self):
        super().__init__("mcp", description="liste les serveurs MCP, leur état et leurs outils ; en relance ou en "
                                            "arrête un", usage="[restart|stop <serveur>]")

    def handle(self, app, arguments: str) -> None:
        """
            Without arguments, send every server of the settings, started or not, with its state and its tools.
            restart starts a server again (one that crashed, failed or was stopped), stop stops it: its tools are
            offered no more
        """
        words: list[str] = arguments.split()
        if not words:
            app.events.dispatch(MCP_SERVERS, servers=app.mcp.describe())
            return
        if words[0] not in ACTIONS or len(words) != 2:
            self.error(app, "usage", f"Usage : /mcp {self.usage}")
            return
        action, name = words
        server = app.mcp.server(name)
        if server is None:
            known: str = ", ".join(server.name for server in app.mcp.servers) or "aucun"
            self.error(app, "unknown", f"Aucun serveur MCP ne s'appelle {name} (les serveurs : {known}).")
            return
        if server.invalid:
            self.error(app, "invalid", f"Le serveur {name} ne peut pas être lancé : {server.error}.")
            return
        server.stop() if action == "stop" else server.restart()
        app.mcp_changed(name, ACTIONS[action])
