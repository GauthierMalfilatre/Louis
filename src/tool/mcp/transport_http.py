##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## MCP HTTP transport (Streamable HTTP): the server runs elsewhere, at an address. Each message is POSTed to it; the
## server answers with JSON, or with a stream of events (SSE) that may carry its own messages before the answer
##
from logger.logger import log
from typing import Callable, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json
import threading

# Seconds a request of the transport waits without a byte from the server, the end of the session included
CLOSE_TIMEOUT: float = 2.0

# The types of an answer the transport reads, as the protocol asks the client to say
ACCEPT: str = "application/json, text/event-stream"

def events(stream) -> Iterator[dict]:
    """
        The messages of a stream of server-sent events, as they come: each event gives its data lines, joined. What is
        not a JSON message is left out
    """
    data: list[str] = []
    for raw in stream:
        line: str = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if line.startswith(":"):
            continue
        if line:
            field, _, value = line.partition(":")
            if field == "data":
                data.append(value[1:] if value.startswith(" ") else value)
            continue
        if data:
            yield from messages("\n".join(data))
            data = []
    if data:
        yield from messages("\n".join(data))

def messages(text: str) -> Iterator[dict]:
    """ The messages of a JSON body: one, or a batch of them """
    try:
        content = json.loads(text)
    except json.JSONDecodeError:
        log.debug(f"[mcp] not a JSON message: {text[:200]}")
        return
    for message in content if isinstance(content, list) else [content]:
        if isinstance(message, dict):
            yield message

class HttpTransport:
    """
        A server reached at its address. Each message is sent from a thread of its own: request() of the client
        waits for its answer as it does with a program. A server that can not be reached any more, or that forgot
        the session, is said stopped: it is started again (initialized) as a program that crashed would be
    """
    def __init__(self, name: str, url: str, headers: dict[str, str] | None = None, timeout: float = 600.0):
        """ Init the transport of a server, not opened yet. headers go with every message (a token...) """
        self.__name    : str             = name
        self.__url     : str             = url
        self.__headers : dict[str, str]  = headers or {}
        self.__timeout : float           = timeout
        self.__receive : Callable[[dict], None] | None = None
        self.__closed  : Callable[[str], None] | None  = None
        self.__opened  : bool            = False
        self.__closing : bool            = False
        # Why the server can not be talked to any more, None while it can
        self.__lost    : str | None      = None
        self.__lock    : threading.Lock  = threading.Lock()
        # What the server gave at initialize: the session to name, the version of the protocol to say
        self.__session : str | None      = None
        self.__version : str | None      = None
        self.__initialize: object        = None
        # The stream the server sends its own messages on, closed with the transport
        self.__listener = None
        self.__error   : str             = ""

    @property
    def started(self) -> bool:
        """ Whether the transport was opened """
        return self.__opened

    @property
    def running(self) -> bool:
        """ Whether the server can be talked to: opened, not closed, not lost """
        return self.__opened and not self.__closing and self.__lost is None

    @property
    def stderr(self) -> str:
        """ The last error of HTTP: why the server can not be talked to, often """
        return self.__error

    @property
    def pid(self) -> None:
        """ No process: Louis did not launch the server """
        return None

    @property
    def label(self) -> str:
        """ Where the server runs, for the log """
        return self.__url

    @property
    def target(self) -> str:
        """ Where the server runs, as the user declared it """
        return self.__url

    def open(self, receive: Callable[[dict], None], closed: Callable[[str], None]) -> None:
        """ Get ready to send: what the server answers goes to receive, closed is told why it can not be talked to """
        if not self.__url.startswith(("http://", "https://")):
            raise OSError(f"l'adresse {self.__url} n'est pas en http:// ou https://")
        self.__receive, self.__closed, self.__opened = receive, closed, True

    def send(self, message: dict) -> None:
        """ Send a message, from a thread of its own: its answer comes to receive. Raises OSError once closed """
        if not self.running:
            raise OSError(self.__lost or "transport closed")
        if message.get("method") == "initialize":
            self.__initialize = message.get("id")
        threading.Thread(target=self.__post, args=(message,), name=f"mcp-{self.__name}-post", daemon=True).start()

    def close(self) -> None:
        """ End the session on the server, and stop listening to it: nothing happens a second time """
        if not self.__opened or self.__closing:
            return
        self.__closing = True
        if self.__session is not None:
            try:
                urlopen(Request(self.__url, headers=self.__headers_of(), method="DELETE"), timeout=CLOSE_TIMEOUT).close()
            except (HTTPError, URLError, OSError, ValueError):
                pass
        listener = self.__listener
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass
        log.info(f"[mcp] {self.__name}: session closed")
        self.__closed("le serveur a été arrêté")

    def __headers_of(self, accept: str = ACCEPT) -> dict[str, str]:
        """ The headers of a message: those of the declaration, the session and the version once agreed """
        headers: dict[str, str] = {"Accept": accept, "User-Agent": "louis-mcp/1.0", **self.__headers}
        if self.__session is not None:
            headers["Mcp-Session-Id"] = self.__session
        if self.__version is not None:
            headers["MCP-Protocol-Version"] = self.__version
        return headers

    def __post(self, message: dict) -> None:
        """
            POST a message, then read what the server answers: nothing (202), a JSON message, or a stream of them that
            ends with the answer. What goes wrong is the answer of the request, an error
        """
        expected = message.get("id") if "method" in message else None
        body: bytes = json.dumps(message, ensure_ascii=False).encode("utf-8")
        request: Request = Request(self.__url, data=body, method="POST",
                                   headers={**self.__headers_of(), "Content-Type": "application/json"})
        try:
            response = urlopen(request, timeout=self.__timeout)
        except HTTPError as e:
            if e.code == 404 and self.__session is not None:
                self.__lose("la session HTTP a expiré sur le serveur")
            self.__fail(expected, f"HTTP {e.code} {e.reason}{self.__hint(e.code)}")
            return
        except (URLError, OSError, ValueError) as e:
            reason = getattr(e, "reason", None) or e
            self.__fail(expected, f"le serveur ne répond pas à {self.__url} ({reason})")
            self.__lose(f"le serveur ne répond plus à {self.__url} ({reason})")
            return
        if message.get("method") == "notifications/initialized":
            # The session is open: what the server sends of its own comes on a stream of its own
            threading.Thread(target=self.__listen, name=f"mcp-{self.__name}-listen", daemon=True).start()
        answered: bool = False
        try:
            with response:
                if expected is not None and expected == self.__initialize:
                    self.__session = response.headers.get("Mcp-Session-Id") or self.__session
                if response.status == 202:
                    return
                stream: bool = response.headers.get_content_type() == "text/event-stream"
                for answer in events(response) if stream else messages(response.read().decode("utf-8", "replace")):
                    self.__deliver(answer)
                    if expected is not None and answer.get("id") == expected and "method" not in answer:
                        answered = True
                        break
        except (OSError, ValueError) as e:
            log.debug(f"[mcp] {self.__name}: the answer was cut ({e})")
        if expected is not None and not answered:
            self.__fail(expected, "le serveur n'a pas donné de réponse")

    def __listen(self) -> None:
        """
            Listen to what the server sends of its own (its tools changed, its logs...) on a stream it keeps open. A
            server that has none says so (405): nothing more is asked
        """
        try:
            response = urlopen(Request(self.__url, headers=self.__headers_of("text/event-stream"), method="GET"),
                               timeout=None)
        except (HTTPError, URLError, OSError, ValueError) as e:
            log.debug(f"[mcp] {self.__name}: no stream of its own ({getattr(e, 'code', None) or e})")
            return
        self.__listener = response
        try:
            with response:
                for message in events(response):
                    self.__deliver(message)
        except (OSError, ValueError):
            pass
        if not self.__closing:
            log.debug(f"[mcp] {self.__name}: its own stream ended")

    def __deliver(self, message: dict) -> None:
        """ A message of the server, to the client. The answer of initialize gives the version said from then on """
        if message.get("id") is not None and message.get("id") == self.__initialize and "result" in message:
            self.__version = (message.get("result") or {}).get("protocolVersion") or self.__version
        self.__receive(message)

    def __fail(self, expected, reason: str) -> None:
        """ The request waits for no answer: it gets the error in its place """
        self.__error = reason
        log.debug(f"[mcp] {self.__name}: {reason}")
        if expected is not None:
            self.__receive({"jsonrpc": "2.0", "id": expected, "error": {"message": reason}})

    def __lose(self, reason: str) -> None:
        """ The server can not be talked to any more: the client is told once, it is started again if it may """
        with self.__lock:
            if self.__lost is not None or self.__closing:
                return
            self.__lost = reason
        log.warning(f"[mcp] {self.__name}: {reason}")
        self.__closed(reason)

    @staticmethod
    def __hint(code: int) -> str:
        """ What the user may do about an error of HTTP """
        if code in (401, 403):
            return " : le serveur refuse l'accès, vérifie le token de ses headers"
        return ""
