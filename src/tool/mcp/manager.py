##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## MCP manager: the servers of the settings (mcp.servers), started with Louis, their tools, stopped when it exits
##
from logger.logger import log
from tool.risk import LEVELS
from tool.mcp.client import McpClient, McpError
from tool.mcp.transport_stdio import StdioTransport
from tool.mcp.tool_mcp import McpTool
import atexit
import shlex
import threading
import time

# The states of a server: it answers; it never did (no such command, an error at its start...); it stopped by
# itself once started; Louis stopped it
RUNNING: str = "running"
FAILED : str = "failed"
CRASHED: str = "crashed"
STOPPED: str = "stopped"

class McpServer:
    """ A server of the settings: how it is launched, how it goes, and its tools once it is started """
    def __init__(self, name: str, command: str, args: list[str], env: dict[str, str], level: str | None):
        """ Init a server, not started yet """
        self.name   : str               = name
        self.command: str               = command
        self.args   : list[str]         = args
        self.env    : dict[str, str]    = env
        self.level  : str | None        = level
        self.client : McpClient | None  = None
        self.tools  : list[McpTool]     = []
        # Why it did not start, None if it did
        self.error  : str | None        = None

    @property
    def state(self) -> str:
        """ How the server goes: running, failed, crashed or stopped """
        if self.error is not None or self.client is None:
            return FAILED
        if self.client.alive:
            return RUNNING
        return CRASHED if self.client.crashed else STOPPED

    def describe(self) -> dict:
        """ What an interface needs to show the server, raw and JSON-friendly """
        return {
            "name"   : self.name,
            "command": shlex.join([self.command, *self.args]) if self.command else "",
            "state"  : self.state,
            "error"  : self.error if self.error is not None else (self.client.why or None) if self.client else None,
            "tools"  : [{"name": tool.name, "remote": tool.remote, "description": tool.about, "risk": tool.level}
                        for tool in self.tools],
        }

class McpManager:
    """
        The MCP servers Louis talks to: each one launched at the start, its tools listed and offered to the model.
        A server that does not start is logged and left out, the others go on. Stopped by close(), else when Louis
        exits: never a process left behind
    """
    def __init__(self, settings: dict):
        """ Init the servers the settings declare: a declaration that is not valid is a server that failed """
        self.__timeout      : float             = float(settings.get("mcp.timeout", 30.0))
        self.__start_timeout: float             = float(settings.get("mcp.start_timeout", 30.0))
        self.__servers      : list[McpServer]   = []
        for entry in settings.get("mcp.servers") or []:
            server: McpServer = self.__declared(entry)
            if server.error is not None:
                log.warning(f"[mcp] {server.name or '?'}: not started, {server.error}")
            self.__servers.append(server)
        atexit.register(self.close)

    def __declared(self, entry) -> McpServer:
        """ A server as the settings declare it: its error says what is wrong with the declaration """
        if not isinstance(entry, dict):
            server: McpServer = McpServer("", "", [], {}, None)
            server.error = "réglage invalide : chaque serveur est un dict {name, command, args, env}"
            return server
        name, command = entry.get("name"), entry.get("command")
        args, env, level = entry.get("args", []), entry.get("env", {}), entry.get("risk")
        server = McpServer(name if isinstance(name, str) else "", command if isinstance(command, str) else "",
                           args if isinstance(args, list) else [], env if isinstance(env, dict) else {},
                           level if level in LEVELS else None)
        if not server.name.strip():
            server.error = "réglage invalide : il lui faut un nom (name)"
        elif any(other.name == server.name for other in self.__servers):
            server.error = f"réglage invalide : un autre serveur s'appelle déjà {server.name}"
        elif not server.command.strip():
            server.error = "réglage invalide : il lui faut une commande à lancer (command)"
        elif not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            server.error = "réglage invalide : args est une liste de textes"
        elif not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
            server.error = "réglage invalide : env est un dict de textes"
        elif level is not None and level not in LEVELS:
            server.error = f"réglage invalide : risk vaut {', '.join(LEVELS)}"
        return server

    def start(self) -> "McpManager":
        """ Start the servers, side by side: one slow to start (npx downloads it the first time) delays none of the others """
        threads: list[threading.Thread] = [
            threading.Thread(target=self.__start, args=(server,), name=f"mcp-start-{server.name}", daemon=True)
            for server in self.__servers if server.error is None
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return self

    def __start(self, server: McpServer) -> None:
        """
            Launch a server, then list its tools, mcp.start_timeout seconds at most for both. What goes wrong is its
            error: the server is stopped and left out
        """
        deadline: float = time.monotonic() + self.__start_timeout
        server.client = McpClient(server.name, StdioTransport(server.name, server.command, server.args, server.env))
        try:
            server.client.start(self.__start_timeout)
            specs: list[dict] = server.client.list_tools(max(1.0, deadline - time.monotonic()))
        except FileNotFoundError:
            server.error = f"la commande {server.command} est introuvable"
        except OSError as e:
            server.error = f"la commande {server.command} ne se lance pas ({e.strerror or e})"
        except McpError as e:
            server.error = str(e)
        except Exception as e:
            log.exception(f"[mcp] {server.name}: start failed")
            server.error = f"{type(e).__name__} : {e}"
        if server.error is not None:
            stderr: str = server.client.stderr
            server.client.close()
            # What it wrote before it stopped tells why, more often than not
            if stderr:
                server.error += f" — {stderr.splitlines()[-1].strip()}"
            log.warning(f"[mcp] {server.name}: not started, {server.error}")
            return
        for spec in specs:
            tool: McpTool = McpTool(server.name, server.client, spec, self.__timeout, server.level)
            if any(known.name == tool.name for known in server.tools):
                log.warning(f"[mcp] {server.name}: {spec['name']} left out, another of its tools is named {tool.name}")
                continue
            server.tools.append(tool)
        log.info(f"[mcp] {server.name}: {len(server.tools)} tools ({', '.join(tool.remote for tool in server.tools)})")

    @property
    def servers(self) -> list[McpServer]:
        """ Get the servers of the settings, started or not """
        return list(self.__servers)

    def tools(self) -> list[McpTool]:
        """ The tools of the servers that started """
        return [tool for server in self.__servers if server.state == RUNNING for tool in server.tools]

    def describe(self) -> list[dict]:
        """ Every server, with its state and its tools: what /mcp shows """
        return [server.describe() for server in self.__servers]

    def close(self) -> None:
        """ Stop every server: nothing happens a second time """
        for server in self.__servers:
            if server.client is not None:
                server.client.close()
