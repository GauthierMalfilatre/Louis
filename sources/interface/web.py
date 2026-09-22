##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Web Interface
##
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import json
import queue
import threading
from interface.interface import Interface

PAGE: Path = Path(__file__).with_name("static") / "index.html"
KEEPALIVE: float = 15.0        # Seconds of silence before pinging a page, which also detects closed ones
SHUTDOWN_TIMEOUT: float = 2.0  # Seconds given to the pages to receive their last events

class WebInterface(Interface):
    """ Chat from a browser: get() waits for a page to send a message, out() streams to every page """

    def __init__(self, host: str = "127.0.0.1", port: int = 8000) -> None:
        super().__init__()
        self.__inputs     : queue.Queue[str | None] = queue.Queue()
        self.__lock       : threading.Condition     = threading.Condition()
        self.__subscribers: set[queue.Queue]        = set()
        # What the pages show, replayed to the ones connecting later
        self.__log        : list[dict]              = []
        self.__waiting    : bool                    = False

        self.__server: ThreadingHTTPServer = ThreadingHTTPServer(
            (host, port), partial(_Handler, web=self)
        )
        threading.Thread(target=self.__server.serve_forever, daemon=True).start()
        print(f"Web interface on http://{host}:{self.__server.server_port}")

    def __enter__(self) -> "WebInterface":
        return self

    def __exit__(self, *_) -> None:
        self.shutdown()

    def get(self) -> str:
        """ Wait for a message sent from a page """
        if not self.isOpen():
            raise EOFError
        self.__publish({"type": "waiting"})
        text: str | None = self.__inputs.get()
        if text is None:
            # Closed while waiting, like Ctrl+D on the CLI
            raise EOFError
        self.__publish({"type": "input", "text": text})
        return text

    def out(self, response: str, *, end: str = "\n", flush: bool = False) -> None:
        """ Show smth on every page, always sent right away """
        if response + end:
            self.__publish({"type": "output", "text": response + end})

    def close(self) -> None:
        """ Close the interface, pages stay connected to get what is shown until shutdown """
        if not self.isOpen():
            return
        super().close()
        self.__inputs.put(None)
        self.__publish({"type": "closed"})

    def shutdown(self) -> None:
        """ Stop the server, once the pages got their last events """
        self.__server.shutdown()
        with self.__lock:
            for events in self.__subscribers:
                events.put(None)
            self.__lock.wait_for(lambda: not self.__subscribers, SHUTDOWN_TIMEOUT)
        self.__server.server_close()

    def submit(self, text: str) -> bool:
        """ Queue a message for get(), refused once closed """
        if not self.isOpen():
            return False
        self.__inputs.put(text)
        return True

    def subscribe(self) -> queue.Queue:
        """ Get the events to show on a page, starting with a snapshot of the current state """
        events: queue.Queue = queue.Queue()
        with self.__lock:
            events.put({
                "type": "snapshot",
                "log": [dict(entry) for entry in self.__log],
                "waiting": self.__waiting,
                "closed": not self.isOpen(),
            })
            self.__subscribers.add(events)
        return events

    def unsubscribe(self, events: queue.Queue) -> None:
        """ Stop sending events to a page """
        with self.__lock:
            self.__subscribers.discard(events)
            self.__lock.notify_all()

    def __publish(self, event: dict) -> None:
        """ Apply an event to the state, then send it to every page """
        with self.__lock:
            if event["type"] == "waiting":
                self.__waiting = True
            elif event["type"] in ("input", "closed"):
                self.__waiting = False
            if event["type"] == "input":
                self.__log.append({"role": "user", "text": event["text"]})
            elif event["type"] == "output":
                # Everything shown between two messages is the answer to the first one
                if not self.__log or self.__log[-1]["role"] != "assistant":
                    self.__log.append({"role": "assistant", "text": ""})
                self.__log[-1]["text"] += event["text"]
            for events in self.__subscribers:
                events.put(event)

class _Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, web: WebInterface, **kwargs) -> None:
        self.__web: WebInterface = web
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args) -> None:
        """ Keep the terminal quiet """

    def do_GET(self) -> None:
        path: str = urlsplit(self.path).path
        if path == "/":
            self.__page()
        elif path == "/api/events":
            self.__events()
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/messages":
            self.send_error(404)
            return
        # JSON only: other sites can't send it here, the browser would need a CORS preflight
        if self.headers.get_content_type() != "application/json":
            self.send_error(415)
            return
        try:
            text = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))["text"]
        except (ValueError, KeyError, TypeError):
            self.send_error(400)
            return
        if not isinstance(text, str) or not text.strip():
            self.send_error(400, "Empty message")
        elif not self.__web.submit(text):
            self.send_error(409, "Interface closed")
        else:
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def __page(self) -> None:
        """ Send the chat page """
        body: bytes = PAGE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def __events(self) -> None:
        """ Stream the events to a page (Server-Sent Events), until shutdown or the page leaves """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        events: queue.Queue = self.__web.subscribe()
        try:
            while True:
                try:
                    event: dict | None = events.get(timeout=KEEPALIVE)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    continue
                if event is None:
                    break
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
        except ConnectionError:
            pass
        finally:
            self.__web.unsubscribe(events)
