##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Web Interface
##
from functools import partial
import base64
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import json
import queue
import threading
from interface.interface import Interface
from model.model import ModelException
from events.events import Event, MODEL_SWITCHED

PAGE: Path = Path(__file__).with_name("static") / "index.html"
KEEPALIVE: float = 15.0        # Seconds of silence before pinging a page, which also detects closed ones
SHUTDOWN_TIMEOUT: float = 2.0  # Seconds given to the pages to receive their last events
DETAIL_LENGTH: int = 60        # Characters shown of a tool argument
IMAGE_TYPES: frozenset = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})
MAX_IMAGE: int = 12 * 1024 * 1024  # Bytes accepted for one image
MAX_IMAGES: int = 24               # Images kept in memory, the oldest are dropped first

def _detail(arguments: dict) -> str:
    """ Sum up what a tool call was given, with its first argument """
    if not isinstance(arguments, dict) or not arguments:
        return ""
    key, value = next(iter(arguments.items()))
    text: str = " ".join(str(value).split())
    return f"{key}={text[:DETAIL_LENGTH]}…" if len(text) > DETAIL_LENGTH else f"{key}={text}"

class WebInterface(Interface):
    """ Chat from a browser: get() waits for a page to send a message, out() streams to every page """

    def __init__(self, host: str = "127.0.0.1", port: int = 8000) -> None:
        super().__init__()
        self.__inputs     : queue.Queue                = queue.Queue()
        self.__lock       : threading.Condition     = threading.Condition()
        self.__subscribers: set[queue.Queue]        = set()
        # What the pages show, replayed to the ones connecting later
        self.__log        : list[dict]              = []
        self.__waiting    : bool                    = False
        self.__info       : dict | None             = None
        self.__session                              = None
        self.__seen       : int                     = 0
        # Images a page uploaded, waiting to be sent with a message
        self.__images     : dict[str, tuple]        = {}
        self.__attachments: list[str]               = []

        self.__server: ThreadingHTTPServer = ThreadingHTTPServer(
            (host, port), partial(_Handler, web=self)
        )
        threading.Thread(target=self.__server.serve_forever, daemon=True).start()
        print(f"Web interface on http://{host}:{self.__server.server_port}")

    def __enter__(self) -> "WebInterface":
        return self

    def __exit__(self, *_) -> None:
        self.shutdown()

    def bind(self, manager) -> "WebInterface":
        """ Give access to the manager, whose info is shown on the pages """
        super().bind(manager)
        manager.events.subscribe(self.__on_event, MODEL_SWITCHED)
        self.__sync_session()
        self.__publish_info()
        return self

    def __on_event(self, event: Event) -> None:
        """ Turn a backend event into a plain-language line shown in the conversation,
            clearly not an answer from the model
        """
        if event.name == MODEL_SWITCHED:
            self.__publish({"type": "system", "text": f"Now using {event.data['current']}"})

    def get(self) -> str:
        """ Wait for a message sent from a page """
        if not self.isOpen():
            raise EOFError
        # The last message may have changed them (/model, /new-session, ...)
        self.__publish_tools()
        self.__sync_session()
        self.__publish_info()
        self.__publish({"type": "waiting"})
        message: tuple | None = self.__inputs.get()
        if message is None:
            # Closed while waiting, like Ctrl+D on the CLI
            raise EOFError
        text, images = message
        self.__attachments = [
            base64.b64encode(self.__images[image][1]).decode()
            for image in images if image in self.__images
        ]
        self.__publish({"type": "input", "text": text, "images": images})
        return text

    def attachments(self) -> list[str]:
        """ The images sent with the last message, base64 encoded for the model API """
        return list(self.__attachments)

    def out(self, response: str, *, end: str = "\n", flush: bool = False) -> None:
        """ Show smth on every page, always sent right away """
        if response + end:
            self.__publish({"type": "output", "text": response + end})

    def debug(self, response, *, end="\n", flush=False):
        print(response, end=end, flush=flush)

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

    def submit(self, text: str, images: list[str] | None = None) -> bool:
        """ Queue a message for get(), with the images uploaded for it """
        if not self.isOpen():
            return False
        self.__inputs.put((text, [image for image in images or [] if image in self.__images]))
        return True

    def store_image(self, content_type: str, data: bytes) -> str:
        """ Keep an image a page uploaded, and get the id to send it back with """
        identifier: str = uuid.uuid4().hex
        self.__images[identifier] = (content_type, data)
        for old in list(self.__images)[:-MAX_IMAGES]:
            del self.__images[old]
        return identifier

    def image(self, identifier: str) -> tuple | None:
        """ Get an uploaded image, to show it on the pages """
        return self.__images.get(identifier)

    def subscribe(self) -> queue.Queue:
        """ Get the events to show on a page, starting with a snapshot of the current state """
        events: queue.Queue = queue.Queue()
        with self.__lock:
            events.put({
                "type": "snapshot",
                "log": [dict(entry) for entry in self.__log],
                "waiting": self.__waiting,
                "closed": not self.isOpen(),
                "info": self.__info,
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
            if event["type"] == "reset":
                self.__log = [dict(entry) for entry in event["log"]]
            elif event["type"] == "tools":
                # The answer they were used for is the last thing shown
                if self.__log and self.__log[-1]["role"] == "assistant":
                    self.__log[-1]["tools"] = event["tools"]
            elif event["type"] == "info":
                self.__info = event["info"]
            elif event["type"] == "system":
                self.__log.append({"role": "system", "text": event["text"]})
            elif event["type"] == "input":
                self.__log.append({
                    "role": "user", "text": event["text"], "images": event.get("images") or []
                })
            elif event["type"] == "output":
                # Everything shown between two messages is the answer to the first one
                if not self.__log or self.__log[-1]["role"] != "assistant":
                    self.__log.append({"role": "assistant", "text": ""})
                self.__log[-1]["text"] += event["text"]
            for events in self.__subscribers:
                events.put(event)

    def __sync_session(self) -> None:
        """ Show the conversation of the manager's session, when it opened another one """
        session = self.manager.session
        if session is self.__session:
            return
        self.__session = session
        # Only what a page can show: the system prompt and the tool results stay hidden,
        # the tools a round called are kept for the answer that followed them
        log  : list[dict] = []
        tools: list[dict] = []
        for message in session.messages:
            if message.role == "user":
                log.append({"role": "user", "text": message.content})
                tools = []
            elif message.role == "assistant":
                if message.content:
                    log.append({"role": "assistant", "text": message.content, "tools": tools})
                    tools = []
                tools = tools + [
                    {"name": call.name, "detail": _detail(call.arguments)}
                    for call in message.tool_calls or []
                ]
        self.__seen = len(session.messages)
        self.__publish({"type": "reset", "log": log})

    def __publish_tools(self) -> None:
        """ Tell the pages which tools the answer used, read from what the session recorded """
        messages = self.manager.session.messages
        tools: list[dict] = [
            {"name": call.name, "detail": _detail(call.arguments)}
            for message in messages[self.__seen:]
            for call in message.tool_calls or []
        ]
        self.__seen = len(messages)
        if tools:
            self.__publish({"type": "tools", "tools": tools})

    def __publish_info(self) -> None:
        """ Send what the pages show about the manager, when it changed """
        commands = self.manager.commandTree
        info: dict = {
            "user": self.manager.user.name,
            # None while the model class says nothing about it
            "vision": getattr(self.manager.model, "vision", None),
            "anonymous": self.manager.user.is_anonymous,
            "session": self.manager.session.id,
            "sessions": self.manager.user.summaries(),
            "model": self.manager.model.model,
            "prefix": commands.prefix,
            "commands": [
                {
                    "name": command.name,
                    "alias": command.alias,
                    "usage": command.usage,
                    "description": command.description,
                }
                for command in commands.commands
            ],
        }
        if info != self.__info:
            self.__publish({"type": "info", "info": info})

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
        elif path == "/api/models":
            self.__models()
        elif path.startswith("/api/images/"):
            self.__image(path.removeprefix("/api/images/"))
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        path: str = urlsplit(self.path).path
        if path == "/api/images":
            self.__upload()
            return
        if path != "/api/messages":
            self.send_error(404)
            return
        # JSON only: other sites can't send it here, the browser would need a CORS preflight
        if self.headers.get_content_type() != "application/json":
            self.send_error(415)
            return
        try:
            body: dict = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            text = body["text"]
            images = body.get("images") or []
        except (ValueError, KeyError, TypeError, AttributeError):
            self.send_error(400)
            return
        if not isinstance(text, str) or not text.strip():
            self.send_error(400, "Empty message")
        elif not isinstance(images, list) or not all(isinstance(i, str) for i in images):
            self.send_error(400, "Bad images")
        elif not self.__web.submit(text, images):
            self.send_error(409, "Interface closed")
        else:
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def __upload(self) -> None:
        """ Store an image a page sent, and answer with the id to send it with a message """
        length: int = int(self.headers.get("Content-Length", 0))
        if self.headers.get_content_type() not in IMAGE_TYPES:
            self.send_error(415, "Images only")
            return
        if length <= 0 or length > MAX_IMAGE:
            self.send_error(413, "Image too large")
            return
        data: bytes = self.rfile.read(length)
        if len(data) != length:
            self.send_error(400, "Truncated image")
            return
        self.__send_json(
            {"id": self.__web.store_image(self.headers.get_content_type(), data)}, status=201
        )

    def __image(self, identifier: str) -> None:
        """ Send back an uploaded image, for the pages to show it """
        stored: tuple | None = self.__web.image(identifier)
        if stored is None:
            self.send_error(404)
            return
        content_type, data = stored
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def __send_json(self, data: dict, *, status: int = 200) -> None:
        """ Answer with a JSON body """
        body: bytes = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def __page(self) -> None:
        """ Send the chat page """
        body: bytes = PAGE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def __models(self) -> None:
        """ Send the models the manager can switch to """
        manager = self.__web.manager
        if manager is None:
            self.send_error(503, "Not ready")
            return
        try:
            models: list[str] = manager.model.available()
        except ModelException as e:
            self.send_error(502, e.message)
            return
        self.__send_json({"models": models})

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
