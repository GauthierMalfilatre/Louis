##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /mcp: the MCP servers declared, their state and their tools; /mcp restart|stop|trust <server> to manage one
##
from command.command import Command
from events.event_list import MCP_SERVERS
from tool.mcp.manager import PENDING

# What /mcp does to a server, by the word typed after it, and the change the user is told
ACTIONS: dict[str, str] = {"restart": "restarted", "stop": "stopped", "trust": "trusted"}

class McpCommand(Command):
    def __init__(self):
        super().__init__("mcp", description="liste les serveurs MCP, leur état et leurs outils ; en relance, en "
                                            "arrête, ou approuve un serveur du projet ou ses outils modifiés",
                         usage="[restart|stop|trust <serveur>]")

    def handle(self, app, arguments: str) -> None:
        """
            Without arguments, send every server declared, started or not, with its state and its tools. restart
            starts a server again (one that crashed, failed, was stopped or is disabled), stop stops it: its tools
            are offered no more. trust starts a server the project declared, once the user read what it runs, or
            takes the tools of a server that changed since they were first listed
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
        if action == "trust":
            self.__trust(app, server)
            return
        if server.state == PENDING:
            self.error(app, "pending", f"Le serveur {name} vient de {server.declaration.source}, un fichier du projet : "
                                       f"/mcp trust {name} pour l'approuver et le lancer.")
            return
        server.stop() if action == "stop" else server.restart()
        app.mcp_changed(name, ACTIONS[action])

    def __trust(self, app, server) -> None:
        """
            Trust a server of the project, as it is declared now, and start it unless its declaration disables it.
            Or take the tools of a server that changed since they were first listed, as they are now
        """
        if server.state != PENDING and server.held:
            server.accept()
            app.mcp_changed(server.name, "accepted")
            return
        if server.state != PENDING:
            self.error(app, "trusted", f"Le serveur {server.name} n'attend pas ton accord.")
            return
        try:
            app.mcp.trust(server)
        except OSError as e:
            self.error(app, "failed", f"Ton accord ne peut pas être gardé dans {app.mcp.trust_file} : "
                                      f"{e.strerror or e}.")
            return
        if server.declaration.enabled:
            server.start()
        app.mcp_changed(server.name, "trusted")
