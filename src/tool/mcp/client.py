##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## MCP client: talk to an MCP server in JSON-RPC 2.0, through its transport (stdio: a program Louis launches)
##
from logger.logger import log
from pathlib import Path
from typing import Callable
import itertools
import json
import logging
import os
import queue
import threading
import time

# The version of the protocol Louis speaks: the server answers with the one it speaks, an older one if it must
PROTOCOL_VERSION: str = "2025-06-18"

# Pages of tools/list read at most: a server that always gives a next cursor never ends the listing
MAX_PAGES: int = 100

# What a server tells changed, by its notification: Louis lists it again before the next message
LIST_CHANGED: dict[str, str] = {
    "notifications/tools/list_changed": "tools",
    "notifications/prompts/list_changed": "prompts",
}

# The levels of the logs of a server (RFC 5424, as MCP names them), and where they go in the log of Louis
LOG_LEVELS: dict[str, int] = {
    "debug": logging.DEBUG, "info": logging.INFO, "notice": logging.INFO, "warning": logging.WARNING,
    "error": logging.ERROR, "critical": logging.ERROR, "alert": logging.ERROR, "emergency": logging.ERROR,
}

# Characters of a log line of a server kept
LOG_LENGTH: int = 500

class McpError(Exception):
    """ The server answered with an error, or can not answer any more (it stopped, it crashed) """

class McpTimeout(McpError):
    """ The server did not answer in time: waited seconds """
    def __init__(self, message: str, waited: float):
        super().__init__(message)
        self.waited: float = waited

class McpClient:
    """
        One MCP server, talked to through its transport. What the server writes comes from another thread: the
        answers go to the request that waits for them, its own requests (ping) are answered there.
        Synchronous for Louis: request() waits for its answer, timeout seconds at most
    """
    def __init__(self, name: str, transport):
        """ Init the client of a server, not started yet: start() opens its transport """
        self.__name     : str                    = name
        self.__transport                         = transport
        self.__ids      : itertools.count        = itertools.count(1)
        # The requests waiting for their answer, by id: filled by the thread that reads the server
        self.__pending  : dict[int, queue.Queue] = {}
        self.__lock     : threading.Lock         = threading.Lock()
        # Why the server can not answer any more, None while it can
        self.__died     : str | None             = None
        # Stopped by close(): its end is no crash
        self.__closed   : bool                   = False
        # What the server said changed since Louis last asked (its tools...): told by the thread that reads it
        self.__changed  : set[str]               = set()
        self.server_info : dict = {}
        self.capabilities: dict = {}

    @property
    def name(self) -> str:
        """ Get the name of the server, as the settings give it """
        return self.__name

    @property
    def transport(self):
        """ Get how the server is reached: the program launched, or its address """
        return self.__transport

    @property
    def alive(self) -> bool:
        """ Whether the server runs and can answer """
        return self.__transport.started and self.__died is None and self.__transport.running

    @property
    def crashed(self) -> bool:
        """ Whether the server stopped by itself once started: Louis did not close it """
        return self.__transport.started and not self.__closed and not self.alive

    @property
    def why(self) -> str:
        """ Why the server can not answer, "" while it can """
        if self.alive:
            return ""
        return self.__died or ("le serveur a été arrêté" if self.__closed else "le serveur n'est pas lancé")

    @property
    def stderr(self) -> str:
        """ The last lines the server wrote on its error output: why it failed, often """
        return self.__transport.stderr

    @property
    def pid(self) -> int | None:
        """ Get the process of the server, None before it is launched or when Louis did not launch it """
        return self.__transport.pid

    def start(self, timeout: float, log_level: str | None = None) -> "McpClient":
        """
            Open the transport (launch the server) and agree with it on the protocol (initialize), timeout seconds at
            most. Raises OSError when the command can not be run, McpError when the server does not answer as it must.
            A server that has logs sends those of log_level and above, to the log of Louis
        """
        self.__transport.open(self.__receive, self.__lost)
        result: dict = self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "louis", "version": "1.0"},
        }, timeout)
        self.server_info = result.get("serverInfo") or {}
        self.capabilities = result.get("capabilities") or {}
        self.notify("notifications/initialized")
        if log_level in LOG_LEVELS and "logging" in self.capabilities:
            try:
                self.request("logging/setLevel", {"level": log_level}, timeout)
            except McpError as e:
                log.debug(f"[mcp] {self.__name}: its logs stay at their level ({e})")
        log.info(f"[mcp] {self.__name}: started ({self.__transport.label}), {self.server_info.get('name', '?')} "
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

    def changes(self) -> set[str]:
        """ What the server said changed since the last time it was asked: its tools, its prompts """
        with self.__lock:
            changed, self.__changed = self.__changed, set()
        return changed

    def call_tool(self, name: str, arguments: dict, timeout: float,
                  on_progress: Callable[[dict], None] | None = None, most: float | None = None) -> dict:
        """
            Call a tool of the server: its result as it gives it, content and isError. With on_progress, the server
            may tell how far it is: on_progress gets each step (progress, total, message), and each one gives it
            timeout seconds more, most seconds in all
        """
        return self.request("tools/call", {"name": name, "arguments": arguments}, timeout, on_progress, most)

    def request(self, method: str, params: dict | None = None, timeout: float = 30.0,
                on_progress: Callable[[dict], None] | None = None, most: float | None = None) -> dict:
        """
            Send a request and wait for its answer, timeout seconds at most: its result. Raises McpTimeout when it
            does not come, McpError when it is an error or the server can not answer. A request the user interrupts
            (Ctrl+C) is cancelled on the server too. With on_progress, the steps the server tells put the wait off
            (see call_tool), most seconds at most: a server that works forever is not waited for forever
        """
        number: int = next(self.__ids)
        answer: queue.Queue = queue.Queue()
        if on_progress is not None:
            # The id of the request is its token: the steps are told to the request that waits for them
            params = {**(params or {}), "_meta": {**(params or {}).get("_meta", {}), "progressToken": number}}
        with self.__lock:
            if self.__died is not None:
                raise McpError(self.__died)
            self.__pending[number] = answer
        sent: float = time.monotonic()
        deadline: float = sent + timeout
        limit: float = sent + max(timeout, most or timeout)
        try:
            self.__send({"jsonrpc": "2.0", "id": number, "method": method, **({"params": params} if params is not None else {})})
            while True:
                try:
                    message: dict = answer.get(timeout=max(0.0, min(deadline, limit) - time.monotonic()))
                except queue.Empty:
                    self.__cancel(number, "timeout")
                    waited: float = time.monotonic() - sent
                    raise McpTimeout(f"pas de réponse à {method} après {waited:.3g} s", waited) from None
                except KeyboardInterrupt:
                    self.__cancel(number, "interrupted by the user")
                    raise
                if message.get("method") != "notifications/progress":
                    break
                # The server works: it is waited for again, as long as at first
                deadline = time.monotonic() + timeout
                if on_progress is not None:
                    on_progress(message.get("params") or {})
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
        """ Stop the server (its transport closed): nothing happens a second time """
        if not self.__transport.started or self.__closed:
            return
        self.__closed = True
        self.__transport.close()

    def __send(self, message: dict) -> None:
        """ Write a message to the server """
        try:
            self.__transport.send(message)
        except (OSError, ValueError) as e:
            raise McpError(self.__died or f"le serveur ne lit plus ses messages ({type(e).__name__})") from None

    def __cancel(self, number: int, reason: str) -> None:
        """ Tell the server a request is not waited for any more: it may stop working on it """
        try:
            self.notify("notifications/cancelled", {"requestId": number, "reason": reason})
        except McpError:
            pass

    def __log(self, entry: dict) -> None:
        """ A log line of the server, in the log of Louis at its level """
        data = entry.get("data")
        text: str = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        logger: str = f" ({entry['logger']})" if entry.get("logger") else ""
        log.log(LOG_LEVELS.get(entry.get("level"), logging.INFO), f"[mcp] {self.__name}{logger}: {text[:LOG_LENGTH]}")

    def __lost(self, reason: str) -> None:
        """ The server can not answer any more: every request still waiting fails, with why """
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
            # A notification: its tools changed are only noted here, they are listed again by the thread of Louis
            if method in LIST_CHANGED:
                with self.__lock:
                    self.__changed.add(LIST_CHANGED[method])
            elif method == "notifications/message":
                self.__log(message.get("params") or {})
                return
            elif method == "notifications/progress":
                # A step of a request still waited for: told to it, in the thread of Louis
                with self.__lock:
                    waiting: queue.Queue | None = self.__pending.get((message.get("params") or {}).get("progressToken"))
                if waiting is not None:
                    waiting.put(message)
                return
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
