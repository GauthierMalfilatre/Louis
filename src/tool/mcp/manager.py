##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## MCP manager: the servers declared (mcp.servers, the .mcp.json files), started with Louis, their tools, stopped when
## it exits
##
from logger.logger import log
from tool.mcp.client import McpClient, McpError
from tool.mcp.config import Declaration, declarations
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
    """
        A server declared: how it is launched, how it goes, and its tools once it is started. It can be stopped and
        started again; one that crashed is started again by itself, restarts times at most
    """
    def __init__(self, declaration: Declaration, *, timeout: float = 30.0, start_timeout: float = 30.0,
                 restarts: int = 0, max_timeout: float = 600.0, log_level: str | None = "info"):
        """
            Init a server, not started yet: its calls wait timeout seconds at most (max_timeout while it tells it
            works on them), its start start_timeout. Its logs of log_level and above go to the log of Louis
        """
        self.declaration: Declaration    = declaration
        self.name    : str               = declaration.name
        self.command : str               = declaration.command
        self.args    : list[str]         = declaration.args
        self.env     : dict[str, str]    = declaration.env
        self.level   : str | None        = declaration.level
        self.timeout : float             = timeout
        self.max_timeout: float          = max(timeout, max_timeout)
        self.log_level  : str | None     = log_level
        self.client  : McpClient | None  = None
        self.tools   : list[McpTool]     = []
        # Why it did not start, None if it did
        self.error   : str | None        = declaration.error
        # Its declaration is not valid (error says why): it can not be started
        self.invalid : bool              = declaration.error is not None
        self.__start_timeout: float      = start_timeout
        # The restarts it may still make by itself, after a crash
        self.__restarts     : int        = max(0, restarts)
        # Started again by itself since its tools were last offered: they may have changed
        self.__renewed      : bool       = False

    @property
    def state(self) -> str:
        """ How the server goes: running, failed, crashed or stopped """
        if self.error is not None or self.client is None:
            return FAILED
        if self.client.alive:
            return RUNNING
        return CRASHED if self.client.crashed else STOPPED

    @property
    def why(self) -> str:
        """ Why the server does not answer, "" while it does """
        if self.error is not None:
            return self.error
        return self.client.why if self.client is not None else "le serveur n'est pas lancé"

    @property
    def restarts(self) -> int:
        """ Get the restarts the server may still make by itself, after a crash """
        return self.__restarts

    def describe(self) -> dict:
        """ What an interface needs to show the server, raw and JSON-friendly """
        return {
            "name"   : self.name,
            "source" : self.declaration.source,
            "command": shlex.join([self.command, *self.args]) if self.command else "",
            "state"  : self.state,
            "error"  : self.error if self.error is not None else (self.client.why or None) if self.client else None,
            "tools"  : [{"name": tool.name, "remote": tool.remote, "description": tool.about, "risk": tool.level}
                        for tool in self.tools],
        }

    def start(self) -> "McpServer":
        """
            Launch the server, then list its tools, start_timeout seconds at most for both. What goes wrong is its
            error: the server is stopped and left out
        """
        if self.invalid:
            return self
        deadline: float = time.monotonic() + self.__start_timeout
        self.error, self.tools = None, []
        self.client = McpClient(self.name, StdioTransport(self.name, self.command, self.args, self.env))
        try:
            self.client.start(self.__start_timeout, self.log_level)
            specs: list[dict] = self.client.list_tools(max(1.0, deadline - time.monotonic()))
        except FileNotFoundError:
            self.error = f"la commande {self.command} est introuvable"
        except OSError as e:
            self.error = f"la commande {self.command} ne se lance pas ({e.strerror or e})"
        except McpError as e:
            self.error = str(e)
        except Exception as e:
            log.exception(f"[mcp] {self.name}: start failed")
            self.error = f"{type(e).__name__} : {e}"
        if self.error is not None:
            stderr: str = self.client.stderr
            self.client.close()
            # What it wrote before it stopped tells why, more often than not
            if stderr:
                self.error += f" — {stderr.splitlines()[-1].strip()}"
            log.warning(f"[mcp] {self.name}: not started, {self.error}")
            return self
        self.tools = self.__offered(specs)
        log.info(f"[mcp] {self.name}: {len(self.tools)} tools ({', '.join(tool.remote for tool in self.tools)})")
        return self

    def stop(self) -> "McpServer":
        """ Stop the server, if it was started: its tools are offered no more """
        if self.client is not None:
            self.client.close()
        return self

    def restart(self) -> "McpServer":
        """ Stop the server and start it again: what it offers is listed again """
        log.info(f"[mcp] {self.name}: restarted")
        return self.stop().start()

    def connect(self) -> McpClient | None:
        """
            The client to call the server with. A server that crashed is started again first, while it may: the
            call that saw it crash is never made again, it may have acted
        """
        if self.client is not None and self.client.crashed and self.__restarts > 0:
            self.__restarts -= 1
            log.warning(f"[mcp] {self.name}: crashed ({self.client.why}), restarted by itself "
                        f"({self.__restarts} restarts left)")
            self.restart()
            self.__renewed = True
        return self.client

    def refresh(self) -> str | None:
        """
            How the tools of the server changed since they were last offered: "restarted" (it started again by
            itself), "tools" (it said they changed: they are listed again), None when they did not
        """
        changed: str | None = "restarted" if self.__renewed else None
        self.__renewed = False
        if self.client is None or not self.client.alive or "tools" not in self.client.changes():
            return changed
        try:
            self.tools = self.__offered(self.client.list_tools(self.timeout))
        except McpError as e:
            log.warning(f"[mcp] {self.name}: its tools changed but can not be listed: {e}")
            return changed
        log.info(f"[mcp] {self.name}: its tools changed, {len(self.tools)} now "
                 f"({', '.join(tool.remote for tool in self.tools)})")
        return changed or "tools"

    def __offered(self, specs: list[dict]) -> list[McpTool]:
        """ The tools of the server, from what tools/list gave: two that would have the same name, the first only """
        tools: list[McpTool] = []
        for spec in specs:
            tool: McpTool = McpTool(self, spec)
            if any(known.name == tool.name for known in tools):
                log.warning(f"[mcp] {self.name}: {spec['name']} left out, another of its tools is named {tool.name}")
                continue
            tools.append(tool)
        return tools

class McpManager:
    """
        The MCP servers Louis talks to: each one launched at the start, its tools listed and offered to the model.
        A server that does not start is logged and left out, the others go on. Stopped by close(), else when Louis
        exits: never a process left behind
    """
    def __init__(self, settings: dict):
        """ Init the servers declared: a declaration that is not valid is a server that failed """
        self.__servers: list[McpServer] = []
        for declaration in declarations(settings):
            server: McpServer = McpServer(
                declaration, timeout=float(settings.get("mcp.timeout", 30.0)),
                start_timeout=float(settings.get("mcp.start_timeout", 30.0)), restarts=int(settings.get("mcp.restarts", 1)),
                max_timeout=float(settings.get("mcp.max_timeout", 600.0)), log_level=settings.get("mcp.log_level", "info")
            )
            if server.error is not None:
                log.warning(f"[mcp] {server.name or '?'}: not started, {server.error}")
            self.__servers.append(server)
        atexit.register(self.close)

    def start(self) -> "McpManager":
        """ Start the servers, side by side: one slow to start (npx downloads it the first time) delays none of the others """
        threads: list[threading.Thread] = [
            threading.Thread(target=server.start, name=f"mcp-start-{server.name}", daemon=True)
            for server in self.__servers if server.error is None
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return self

    @property
    def servers(self) -> list[McpServer]:
        """ Get the servers of the settings, started or not """
        return list(self.__servers)

    def server(self, name: str) -> McpServer | None:
        """ Get the server of that name, None if the settings declare none """
        return next((server for server in self.__servers if server.name == name), None)

    def tools(self) -> list[McpTool]:
        """ The tools of the servers that started """
        return [tool for server in self.__servers if server.state == RUNNING for tool in server.tools]

    def refresh(self) -> list[tuple[McpServer, str]]:
        """ The servers whose tools changed since they were last offered, with how: started again, listed again """
        changes = ((server, server.refresh()) for server in self.__servers)
        return [(server, change) for server, change in changes if change is not None]

    def describe(self) -> list[dict]:
        """ Every server, with its state and its tools: what /mcp shows """
        return [server.describe() for server in self.__servers]

    def close(self) -> None:
        """ Stop every server: nothing happens a second time """
        for server in self.__servers:
            server.stop()
