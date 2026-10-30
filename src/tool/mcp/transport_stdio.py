##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## MCP stdio transport: the server is a program Louis launches, talked to on its standard input and output, one
## JSON message per line
##
from logger.logger import log
from collections import deque
from typing import Callable
import json
import os
import shlex
import signal
import subprocess
import threading

# What a server gets of the environment of Louis, as the official SDK does: what a program needs to run (npx, uvx),
# never the secrets Louis may hold (a token of GitHub...). The env of its settings is added to it
INHERITED_ENV: tuple[str, ...] = ("HOME", "PATH", "USER", "LOGNAME", "SHELL", "TERM", "LANG", "LC_ALL", "TZ", "TMPDIR")

# Seconds a server has to exit once its input is closed, then once it is terminated, before it is killed
STOP_GRACE: float = 2.0

# Lines of the error output of a server kept, to tell why it did not start (npx: the package does not exist...)
STDERR_LINES: int = 5

class StdioTransport:
    """
        A server launched by Louis, in its own session: a Ctrl+C in the terminal cancels a turn of Louis, never its
        servers. A thread reads what it writes, another its error output, to the log
    """
    def __init__(self, name: str, command: str, args: list[str] | None = None, env: dict[str, str] | None = None):
        """ Init the transport of a server, not launched yet: open() launches it """
        self.__name   : str                     = name
        self.__command: list[str]               = [command, *(args or [])]
        self.__env    : dict[str, str]          = {**{key: os.environ[key] for key in INHERITED_ENV if key in os.environ},
                                                   **(env or {})}
        self.__process: subprocess.Popen | None = None
        self.__write  : threading.Lock          = threading.Lock()
        # Stopped by close(): its end is no crash
        self.__closing: bool                    = False
        self.__stderr : deque[str]              = deque(maxlen=STDERR_LINES)

    @property
    def started(self) -> bool:
        """ Whether the server was launched """
        return self.__process is not None

    @property
    def running(self) -> bool:
        """ Whether the process of the server runs """
        return self.__process is not None and self.__process.poll() is None

    @property
    def stderr(self) -> str:
        """ The last lines the server wrote on its error output: why it failed, often """
        return "\n".join(self.__stderr)

    @property
    def pid(self) -> int | None:
        """ Get the process of the server, None before it is launched """
        return self.__process.pid if self.__process is not None else None

    @property
    def label(self) -> str:
        """ Where the server runs, for the log """
        return f"pid {self.pid}"

    @property
    def target(self) -> str:
        """ What runs the server, as the user would type it """
        return shlex.join(self.__command)

    def open(self, receive: Callable[[dict], None], closed: Callable[[str], None]) -> None:
        """
            Launch the server: what it writes goes to receive, one message at a time, and closed is told why once
            it stops. Raises OSError when the command can not be run
        """
        self.__process = subprocess.Popen(
            self.__command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=os.getcwd(), env=self.__env, start_new_session=True
        )
        threading.Thread(target=self.__read, args=(receive, closed), name=f"mcp-{self.__name}", daemon=True).start()
        threading.Thread(target=self.__drain, name=f"mcp-{self.__name}-err", daemon=True).start()

    def send(self, message: dict) -> None:
        """ Write a message to the server, on one line. Raises OSError or ValueError when it reads no more """
        line: bytes = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        with self.__write:
            self.__process.stdin.write(line)
            self.__process.stdin.flush()

    def close(self) -> None:
        """
            Stop the server as the protocol says: its input closed, it should exit; else it is terminated, then
            killed, with every process it started (npx runs node). Nothing happens a second time
        """
        process: subprocess.Popen | None = self.__process
        if process is None or self.__closing:
            return
        self.__closing = True
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

    def __read(self, receive: Callable[[dict], None], closed: Callable[[str], None]) -> None:
        """ Read what the server writes, until it stops: then closed is told why """
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
                    receive(message)
        except (OSError, ValueError):
            pass
        try:
            code: int | None = self.__process.wait(STOP_GRACE)
        except subprocess.TimeoutExpired:
            code = None
        reason: str = "le serveur a été arrêté" if self.__closing else \
            f"le serveur s'est arrêté{f' (code {code})' if code is not None else ''}"
        if not self.__closing:
            log.warning(f"[mcp] {self.__name}: {reason}{f': {self.stderr}' if self.stderr else ''}")
        closed(reason)

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
