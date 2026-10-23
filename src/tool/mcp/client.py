##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## MCP client: talk to an MCP server over stdio, in JSON-RPC 2.0, one message per line
##
from logger.logger import log
from collections import deque
from pathlib import Path
import itertools
import json
import os
import queue
import signal
import subprocess
import threading

# The version of the protocol Louis speaks: the server answers with the one it speaks, an older one if it must
PROTOCOL_VERSION: str = "2025-06-18"

# What a server gets of the environment of Louis, as the official SDK does: what a program needs to run (npx, uvx),
# never the secrets Louis may hold (a token of GitHub...). The env of its settings is added to it
INHERITED_ENV: tuple[str, ...] = ("HOME", "PATH", "USER", "LOGNAME", "SHELL", "TERM", "LANG", "LC_ALL", "TZ", "TMPDIR")

# Seconds a server has to exit once its input is closed, then once it is terminated, before it is killed
STOP_GRACE: float = 2.0

# Pages of tools/list read at most: a server that always gives a next cursor never ends the listing
MAX_PAGES: int = 100

# Lines of the error output of a server kept, to tell why it did not start (npx: the package does not exist...)
STDERR_LINES: int = 5

class McpError(Exception):
    """ The server answered with an error, or can not answer any more (it stopped, it crashed) """

class McpTimeout(McpError):
    """ The server did not answer in time """

class McpClient:
    """
        One MCP server, launched by Louis and talked to on its standard input and output. A thread reads what it
        writes: the answers go to the request that waits for them, its own requests (ping) are answered there.
        Synchronous for Louis: request() waits for its answer, timeout seconds at most
    """
    def __init__(self, name: str, command: str, args: list[str] | None = None, env: dict[str, str] | None = None):
        """ Init the client of a server, not started yet: start() launches it """
        self.__name   : str                 = name
        self.__command: list[str]           = [command, *(args or [])]
        self.__env    : dict[str, str]      = {**{key: os.environ[key] for key in INHERITED_ENV if key in os.environ},
                                               **(env or {})}
        self.__process: subprocess.Popen | None = None
        self.__ids    : itertools.count     = itertools.count(1)
        # The requests waiting for their answer, by id: filled by the thread that reads the server
        self.__pending: dict[int, queue.Queue] = {}
        self.__lock   : threading.Lock      = threading.Lock()
        self.__write  : threading.Lock      = threading.Lock()
        # Why the server can not answer any more, None while it can
        self.__died   : str | None          = None
        # Stopped by close(): its end is no crash
        self.__closed : bool                = False
        self.__stderr : deque[str]          = deque(maxlen=STDERR_LINES)
        self.server_info : dict = {}
        self.capabilities: dict = {}

    @property
    def name(self) -> str:
        """ Get the name of the server, as the settings give it """
        return self.__name

    @property
    def alive(self) -> bool:
        """ Whether the server runs and can answer """
        return self.__process is not None and self.__died is None and self.__process.poll() is None

    @property
    def crashed(self) -> bool:
        """ Whether the server stopped by itself once started: Louis did not close it """
        return self.__process is not None and not self.__closed and not self.alive

    @property
    def why(self) -> str:
        """ Why the server can not answer, "" while it can """
        if self.alive:
            return ""
        return self.__died or ("le serveur a été arrêté" if self.__closed else "le serveur n'est pas lancé")

    @property
    def stderr(self) -> str:
        """ The last lines the server wrote on its error output: why it failed, often """
        return "\n".join(self.__stderr)

    @property
    def pid(self) -> int | None:
        """ Get the process of the server, None before it is launched """
        return self.__process.pid if self.__process is not None else None

    def start(self, timeout: float) -> "McpClient":
        """
            Launch the server and agree with it on the protocol (initialize), timeout seconds at most.
            Raises OSError when the command can not be run, McpError when the server does not answer as it must.
            In its own session: a Ctrl+C in the terminal cancels a turn of Louis, never its servers
        """
        self.__process = subprocess.Popen(
            self.__command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=os.getcwd(), env=self.__env, start_new_session=True
        )
        threading.Thread(target=self.__read, name=f"mcp-{self.__name}", daemon=True).start()
        threading.Thread(target=self.__drain, name=f"mcp-{self.__name}-err", daemon=True).start()
        result: dict = self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "louis", "version": "1.0"},
        }, timeout)
        self.server_info = result.get("serverInfo") or {}
        self.capabilities = result.get("capabilities") or {}
        self.notify("notifications/initialized")
        log.info(f"[mcp] {self.__name}: started (pid {self.pid}), {self.server_info.get('name', '?')} "
                 f"{self.server_info.get('version', '')}, protocol {result.get('protocolVersion')}")
        return self

    def list_tools(self, timeout: float) -> list[dict]:
        """ The tools of the server, every page of them: none if it does not say it has some """
        if "tools" not in self.capabilities:
            return []
        tools: list[dict] = []
        cursor: str | None = None
        for _ in range(MAX_PAGES):
            result: dict = self.request("tools/list", {"cursor": cursor} if cursor else {}, timeout)
            tools += [tool for tool in result.get("tools") or [] if isinstance(tool, dict) and tool.get("name")]
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return tools

    def call_tool(self, name: str, arguments: dict, timeout: float) -> dict:
        """ Call a tool of the server: its result as it gives it, content and isError """
        return self.request("tools/call", {"name": name, "arguments": arguments}, timeout)

    def request(self, method: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        """
            Send a request and wait for its answer, timeout seconds at most: its result. Raises McpTimeout when it
            does not come, McpError when it is an error or the server can not answer. A request the user interrupts
            (Ctrl+C) is cancelled on the server too
        """
        number: int = next(self.__ids)
        answer: queue.Queue = queue.Queue(maxsize=1)
        with self.__lock:
            if self.__died is not None:
                raise McpError(self.__died)
            self.__pending[number] = answer
        try:
            self.__send({"jsonrpc": "2.0", "id": number, "method": method, **({"params": params} if params is not None else {})})
            try:
                message: dict = answer.get(timeout=timeout)
            except queue.Empty:
                self.__cancel(number, "timeout")
                raise McpTimeout(f"pas de réponse à {method} après {timeout:g} s") from None
            except KeyboardInterrupt:
                self.__cancel(number, "interrupted by the user")
                raise
        finally:
            with self.__lock:
                self.__pending.pop(number, None)
        if "error" in message:
            error = message["error"]
            raise McpError((error.get("message") or json.dumps(error, ensure_ascii=False)) if isinstance(error, dict) else str(error))
        result = message.get("result")
        return result if isinstance(result, dict) else {}

    def notify(self, method: str, params: dict | None = None) -> None:
        """ Send a notification: the server answers none """
        self.__send({"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})})

    def close(self) -> None:
        """
            Stop the server as the protocol says: its input closed, it should exit; else it is terminated, then
            killed, with every process it started (npx runs node). Nothing happens a second time
        """
        process: subprocess.Popen | None = self.__process
        if process is None or self.__closed:
            return
        self.__closed = True
        try:
            process.stdin.close()
        except OSError:
            pass
        for stop in (None, signal.SIGTERM, signal.SIGKILL):
            if stop is not None:
                self.__signal(process, stop)
            try:
                process.wait(STOP_GRACE)
                break
            except subprocess.TimeoutExpired:
                continue
        # Its group too: what it started may outlive it
        self.__signal(process, signal.SIGTERM)
        log.info(f"[mcp] {self.__name}: stopped (code {process.returncode})")

    @staticmethod
    def __signal(process: subprocess.Popen, number: int) -> None:
        """ Send a signal to the server and the processes it started, in the session it leads """
        try:
            os.killpg(process.pid, number)
        except (ProcessLookupError, PermissionError):
            pass
        except AttributeError:
            # No process groups (Windows): the server alone
            if process.poll() is None:
                process.send_signal(number)

    def __send(self, message: dict) -> None:
        """ Write a message to the server, on one line """
        line: bytes = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        with self.__write:
            try:
                self.__process.stdin.write(line)
                self.__process.stdin.flush()
            except (OSError, ValueError) as e:
                raise McpError(self.__died or f"le serveur ne lit plus ses messages ({type(e).__name__})") from None

    def __cancel(self, number: int, reason: str) -> None:
        """ Tell the server a request is not waited for any more: it may stop working on it """
        try:
            self.notify("notifications/cancelled", {"requestId": number, "reason": reason})
        except McpError:
            pass

    def __read(self) -> None:
        """ Read what the server writes, until it stops: every request still waiting then fails """
        try:
            for raw in self.__process.stdout:
                line: str = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    log.debug(f"[mcp] {self.__name}: not JSON on its output: {line[:200]}")
                    continue
                if isinstance(message, dict):
                    self.__receive(message)
        except (OSError, ValueError):
            pass
        try:
            code: int | None = self.__process.wait(STOP_GRACE)
        except subprocess.TimeoutExpired:
            code = None
        reason: str = "le serveur a été arrêté" if self.__closed else \
            f"le serveur s'est arrêté{f' (code {code})' if code is not None else ''}"
        if not self.__closed:
            log.warning(f"[mcp] {self.__name}: {reason}{f': {self.stderr}' if self.stderr else ''}")
        with self.__lock:
            self.__died = self.__died or reason
            for answer in self.__pending.values():
                answer.put({"error": {"message": self.__died}})

    def __receive(self, message: dict) -> None:
        """ An answer goes to the request that waits for it; a request of the server is answered at once """
        if "method" not in message:
            with self.__lock:
                answer: queue.Queue | None = self.__pending.get(message.get("id"))
            if answer is not None:
                answer.put(message)
            return
        method: str = message["method"]
        if "id" not in message:
            # A notification: its logs, its list of tools changed... Louis lists the tools once, at the start
            log.debug(f"[mcp] {self.__name}: {method} {json.dumps(message.get('params'), ensure_ascii=False)[:300]}")
            return
        reply: dict = {"jsonrpc": "2.0", "id": message["id"]}
        if method == "ping":
            reply["result"] = {}
        elif method == "roots/list":
            # The folder Louis works in: the only one it gives the model
            reply["result"] = {"roots": [{"uri": Path(os.getcwd()).as_uri(), "name": os.path.basename(os.getcwd())}]}
        else:
            reply["error"] = {"code": -32601, "message": f"Method not found: {method}"}
        try:
            self.__send(reply)
        except McpError:
            pass

    def __drain(self) -> None:
        """ Read what the server writes on its error output, to the log: never to the terminal, nor left to fill up """
        try:
            for raw in self.__process.stderr:
                line: str = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    self.__stderr.append(line)
                    log.debug(f"[mcp] {self.__name}: {line}")
        except (OSError, ValueError):
            pass
