##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Web interface: Louis in a browser (louis --web), and the pages of the public links of /share
##
from interface.interface import Interface
from interface.cli import LABELS, call_detail, result_summary, short_path, preview as one_line
from events.event_bus import EventBus
from events.event import Event
from events.event_list import APP_STARTED, APP_STOPPED, THINKING_ENABLED, THINKING_DISABLED
from events.event_list import CHAT_TURN_STARTED, CHAT_TURN_ENDED, CHAT_TEXT, CHAT_REPLY, CHAT_THINKING
from events.event_list import CHAT_CONTEXT, CHAT_COMPACTED, STRUCTURED_REPLY, GUARD_TRIGGERED
from events.event_list import TOOL_CALL_STARTED, TOOL_CALL_ENDED, TOOL_BEGFOR_PERMISSION, TOOL_GRANT_PERMISSION
from events.event_list import SESSION_CREATED, SESSION_SAVED, SESSION_LIST, SESSION_RESUMED
from events.event_list import EXPORT_DONE, SHARE_CREATED, SHARE_LIST, SHARE_REVOKED, SCHEMA_LIST
from events.event_list import COMMAND_UNKNOWN, COMMAND_ERROR
from events.event_list import RAG_INDEXING, RAG_INDEX_PROGRESS, RAG_DESCRIBE_PROGRESS, RAG_INDEXED, RAG_SOURCES
from events.event_list import RAG_FORGOTTEN
from export.render_html import MARKDOWN, render
from session.database import Database, now
from share import store
from logger.logger import log
from contextlib import closing
from datetime import datetime, timezone
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import ipaddress
import itertools
import json
import os
import queue
import re
import signal
import socket
import sqlite3
import sys
import threading

HOST: str = "127.0.0.1"
# The port of share.base_url when it is empty: the links of /share lead to louis --web by default
PORT: int = 8080

PAGE: Path = Path(__file__).with_name("static") / "index.html"
KEEPALIVE  : float = 15.0          # Seconds of silence before a page is pinged, which also finds the closed ones
MAX_BODY   : int   = 1024 * 1024   # Bytes of a request from a page
RESULT_SHOWN: int  = 20000         # Characters of the result of a tool a page can unfold

# The token of a link, as share.store makes them: nothing else is looked up
TOKEN: re.Pattern = re.compile(r"[A-Za-z0-9_-]{16,64}")
# The answers to a permission: yes, no, always for this tool in this session
CHOICES: frozenset[str] = frozenset({"y", "n", "a"})
# An address that listens on every interface: the links name the computer as localhost
WILDCARDS: frozenset[str] = frozenset({"", "0.0.0.0", "::"})
# The names a page of this computer reaches Louis by, when it only listens there
LOCAL_NAMES: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})

# The chat page loads its fonts and its Markdown libraries from these, nothing else: a reply that slipped a <script>
# past DOMPurify could not send the conversation anywhere
PAGE_POLICY: str = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
)
# A shared page has no script, and reaches nothing: whatever the session holds stays text
SHARE_POLICY: str = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'none'"

NOT_FOUND: str = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lien introuvable</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;font:15px/1.6 system-ui,sans-serif;
background:#faf9fc;color:#1a1721}@media(prefers-color-scheme:dark){body{background:#131017;color:#ece8f3}}
main{max-width:420px;padding:24px;text-align:center}h1{font-size:20px;margin:0 0 6px}p{margin:0;opacity:.7}</style>
</head><body><main><h1>Lien introuvable</h1><p>Ce lien n'existe pas, ou il a été fermé.</p></main></body></html>"""

def markdown(text: str) -> str:
    """ A reply of the model as HTML: the HTML it holds is shown as text, never run """
    return MARKDOWN.render(text)

def home(text: str) -> str:
    """ A message with ~ for the home folder in its paths """
    return text.replace(os.path.expanduser("~") + os.sep, "~" + os.sep)

def plural(count: int, word: str) -> str:
    """ 3 fichiers, 1 fichier """
    return f"{count} {word}{'s' if count > 1 else ''}"

def local(stamp: str | None) -> str:
    """ A date of the database (UTC) in the time of the user: 06/10 14:32 """
    try:
        return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone().strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return stamp or ""

def tool_item(name: str, arguments: dict, producer: str = "model") -> dict:
    """ A tool call as a page shows it while it runs: what it does, on what, and who asked for it """
    return {
        "kind": "tool", "name": name, "label": LABELS.get(name, name), "producer": producer, "status": "running",
        "detail": call_detail(name, arguments if isinstance(arguments, dict) else {}),
    }

def tool_result(name: str, result: str | None, ok: bool | None, duration: float | None = None) -> dict:
    """ What a call gave, in a few words, and the start of its result for the page to unfold """
    if result is None:
        return {"status": "cancelled"}
    shown: str = result if len(result) <= RESULT_SHOWN else result[:RESULT_SHOWN] + "\n…"
    return {"status": "ok" if ok else "failed", "summary": result_summary(name, result, bool(ok)),
            "duration": duration, "result": shown}

def history_items(history: list[dict]) -> list[dict]:
    """
        A resumed session as a page shows it (export.document.conversation): what the user said, the replies of the
        model, and the tool calls of each reply with what they gave
    """
    items: list[dict] = []
    for message in history:
        content: str = (message.get("content") or "").strip()
        if message["role"] == "user":
            items.append({"kind": "user", "text": content})
        elif message["role"] == "assistant":
            if content:
                items.append({"kind": "text", "text": content, "html": markdown(content), "done": True})
            for call in message.get("tools") or []:
                items.append({**tool_item(call["name"], call.get("arguments") or {}),
                              **tool_result(call["name"], call.get("result"), call.get("ok"))})
    return items

def sidebar(sessions: list[dict]) -> list[dict]:
    """ The sessions of SESSION_LIST as the sidebar lists them: the newest first, named by their first message """
    return [{
        "id"        : session["id"],
        "title"     : (session["first_message"] or "").strip().split("\n", 1)[0] or "(vide)",
        "created_at": session["created_at"],
        "here"      : session["here"],
        "cwd"       : short_path(session["cwd"]),
    } for session in reversed(sessions)]

def loopback(host: str) -> bool:
    """ Whether the address only listens on this computer """
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False

class WebInterface(Interface):
    """
        Louis in a browser: getUserInput() waits for a message sent from a page, and every page follows what happens,
        sent as it comes (Server-Sent Events). A page asks the permissions, and its Stop button cancels what Louis is
        doing as Ctrl+C does in a terminal. The same server gives the pages of the public links of /share (/s/<token>)
    """
    def __init__(self, host: str = HOST, port: int = PORT, database: str | None = None):
        """ Listen on host:port at once (OSError when it is taken), the pages are served once opened """
        super().__init__()
        self.__lock       : threading.RLock  = threading.RLock()
        self.__subscribers: set[queue.Queue] = set()
        # What the pages show, given whole to a page that connects, then changed by the operations sent to all
        self.__log  : list[dict]     = []
        self.__items: dict[int, dict] = {}
        self.__ids  : itertools.count = itertools.count(1)
        self.__state: dict = {
            "user": None, "persistent": False, "session": None, "sessions": [], "model": None, "think": False,
            "commands": [], "context": None, "busy": False, "turn": False, "asking": False, "closed": False,
        }
        # The messages of the pages, and their answer to the permission being asked (its id, None when none is)
        self.__inputs : queue.Queue = queue.Queue()
        self.__answers: queue.Queue = queue.Queue()
        self.__asking : int | None  = None

        # Only touched by the main thread, the one of the app
        self.__bus          : EventBus | None = None
        self.__always       : set[str]   = set()
        self.__working      : bool       = False   # A message was taken: the app is on it
        self.__interruptible: bool       = False   # The app is inside what Ctrl+C cancels: the Stop button may
        self.__quiet        : bool       = False   # The /sessions of the sidebar, not shown in the conversation
        self.__listed       : bool       = False
        self.__question     : str        = ""
        self.__text         : int | None = None    # The reply being written, the thinking, the indexing, by id
        self.__thinking     : int | None = None
        self.__progress     : int | None = None
        self.__running      : list[tuple[int, str]] = []

        self.__database: str | None = database
        self.__host    : str        = host
        self.__names   : frozenset[str] | None = LOCAL_NAMES | {host.lower()} if loopback(host) else None
        self.__server  : _Server    = _Server((host, port), partial(_Handler, web=self))
        self.__thread  : threading.Thread | None = None
        self.__stoppable: bool = False
        self.__previous = None

    @property
    def url(self) -> str:
        """ The address of the pages """
        host: str = "localhost" if self.__host in WILDCARDS else f"[{self.__host}]" if ":" in self.__host else self.__host
        return f"http://{host}:{self.__server.server_port}"

    @property
    def names(self) -> frozenset[str] | None:
        """ The host names a page may use, None for any (Louis listens on the network) """
        return self.__names

    def __enter__(self) -> "WebInterface":
        """ Serve the pages, and let their Stop button interrupt the app """
        stop = getattr(signal, "SIGUSR1", None)
        if stop is not None and threading.current_thread() is threading.main_thread():
            self.__previous = signal.signal(stop, self.__on_stop)
            self.__stoppable = True
        self.__thread = threading.Thread(target=self.__server.serve_forever, name="louis-web", daemon=True)
        self.__thread.start()
        log.info(f"[web] serving on {self.url}")
        print(f"Louis est sur {self.url} (Ctrl+C pour l'arrêter)", flush=True)
        if self.__names is None:
            sys.stderr.write("Attention : l'interface est ouverte au réseau, sans mot de passe : qui l'atteint peut "
                             "faire agir Louis sur tes fichiers.\n")
        return self

    def __exit__(self, *exception) -> None:
        """ Tell the pages Louis stopped, then close the server """
        with self.__lock:
            self.__emit({"type": "state", "state": {"closed": True, "busy": False, "turn": False, "asking": False}})
            for events in self.__subscribers:
                events.put(None)
        self.__inputs.put(None)
        if self.__thread is not None:
            self.__server.shutdown()
        self.__server.server_close()
        if self.__stoppable:
            signal.signal(signal.SIGUSR1, self.__previous if self.__previous is not None else signal.SIG_DFL)
            self.__stoppable = False
        log.info("[web] stopped")

    def bind(self, bus: EventBus) -> "WebInterface":
        """ Show everything the app tells, and ask the permissions to the pages """
        self.__bus = bus
        bus.subscribe(self.__on_any)
        bus.subscribe(self.__on_started, APP_STARTED)
        bus.subscribe(lambda event: self.__set(closed=True), APP_STOPPED)
        bus.subscribe(self.__on_session_created, SESSION_CREATED)
        bus.subscribe(self.__on_session_saved, SESSION_SAVED)
        bus.subscribe(self.__on_session_resumed, SESSION_RESUMED)
        bus.subscribe(self.__on_session_list, SESSION_LIST)
        bus.subscribe(self.__on_turn_started, CHAT_TURN_STARTED)
        bus.subscribe(self.__on_thinking, CHAT_THINKING)
        bus.subscribe(self.__on_text, CHAT_TEXT)
        bus.subscribe(self.__on_reply, CHAT_REPLY)
        bus.subscribe(self.__on_turn_ended, CHAT_TURN_ENDED)
        bus.subscribe(self.__on_context, CHAT_CONTEXT)
        bus.subscribe(self.__on_compacted, CHAT_COMPACTED)
        bus.subscribe(self.__on_structured, STRUCTURED_REPLY)
        bus.subscribe(self.__on_tool_started, TOOL_CALL_STARTED)
        bus.subscribe(self.__on_tool_ended, TOOL_CALL_ENDED)
        bus.subscribe(self.__on_permission, TOOL_BEGFOR_PERMISSION)
        bus.subscribe(self.__on_guard, GUARD_TRIGGERED)
        bus.subscribe(self.__on_thinking_switched, THINKING_ENABLED, THINKING_DISABLED)
        bus.subscribe(self.__on_export_done, EXPORT_DONE)
        bus.subscribe(self.__on_share_created, SHARE_CREATED)
        bus.subscribe(self.__on_share_list, SHARE_LIST)
        bus.subscribe(lambda event: self.__notice(f"Lien fermé : {event.data['url']}", "success"), SHARE_REVOKED)
        bus.subscribe(self.__on_schema_list, SCHEMA_LIST)
        bus.subscribe(self.__on_command_unknown, COMMAND_UNKNOWN)
        bus.subscribe(self.__on_command_error, COMMAND_ERROR)
        bus.subscribe(self.__on_rag_indexing, RAG_INDEXING)
        bus.subscribe(self.__on_rag_progress, RAG_INDEX_PROGRESS, RAG_DESCRIBE_PROGRESS)
        bus.subscribe(self.__on_rag_indexed, RAG_INDEXED)
        bus.subscribe(self.__on_rag_sources, RAG_SOURCES)
        bus.subscribe(lambda event: self.__notice(
            f"Source « {event.data['source']} » retirée ({plural(event.data['chunks'], 'passage')})."
        ), RAG_FORGOTTEN)
        return self

    def getUserInput(self) -> str:
        """ Wait for a message sent from a page: EOFError once the server is closed """
        self.__working = self.__interruptible = self.__quiet = False
        if self.__state["persistent"] and not self.__listed:
            # The sessions of the sidebar, asked once as the user would: the events keep them up to date after
            self.__listed = self.__quiet = True
            return "/sessions"
        with self.__lock:
            # A message sent meanwhile is taken at once: Louis never looks free in between
            if self.__inputs.empty():
                self.__emit({"type": "state", "state": {"busy": False, "turn": False, "asking": False}})
        message: tuple[str, bool] | None = self.__inputs.get()
        if message is None:
            raise EOFError
        text, shown = message
        self.__question = text
        if shown:
            self.__add(kind="user", text=text)
        self.__working = True
        return text

    # ---------- Called by the pages, from the threads of the server ----------

    def subscribe(self) -> queue.Queue:
        """ The operations to send to a new page, the first one being everything shown until now """
        events: queue.Queue = queue.Queue()
        with self.__lock:
            events.put(json.dumps({"type": "snapshot", "log": self.__log, "state": self.__state}, ensure_ascii=False))
            self.__subscribers.add(events)
        return events

    def unsubscribe(self, events: queue.Queue) -> None:
        """ A page left """
        with self.__lock:
            self.__subscribers.discard(events)

    def submit(self, text: str, shown: bool = True) -> str | None:
        """
            A message for the app, sent from a page: None once taken, else why it was not. shown False for what a
            button sends (/think, /resume <id>...): its result is shown, not the command
        """
        with self.__lock:
            if self.__state["closed"]:
                return "Louis s'est arrêté."
            if self.__state["busy"]:
                return "Louis travaille encore : attends qu'il ait fini, ou arrête-le."
            self.__emit({"type": "state", "state": {"busy": True}})
            self.__inputs.put((text, shown))
        return None

    def answer(self, request: int, choice: str) -> bool:
        """ The answer of a page to the permission asked (y, n or a), False if it is not the one being asked """
        with self.__lock:
            if request != self.__asking:
                return False
            self.__asking = None
            self.__answers.put(choice)
        return True

    def stop(self) -> bool:
        """ Cancel what the app is doing, as Ctrl+C: the signal is handled by the main thread, the one of the app """
        with self.__lock:
            busy: bool = self.__state["busy"]
        if not busy or not self.__stoppable:
            return False
        signal.pthread_kill(threading.main_thread().ident, signal.SIGUSR1)
        return True

    def shared(self, token: str) -> dict | None:
        """ The document of a public link, None if there is no such open link """
        if self.__database is None:
            return None
        try:
            with closing(Database(self.__database, readonly=True)) as db:
                return store.get(db, token)
        except sqlite3.Error as e:
            log.warning(f"[web] cannot read the share {token[:6]}…: {e}")
            return None

    # ---------- What the pages show ----------

    def __emit(self, operation: dict) -> None:
        """ Apply an operation to what is shown, then send it to every page, in the order they are made """
        with self.__lock:
            self.__apply(operation)
            data: str = json.dumps(operation, ensure_ascii=False)
            for events in self.__subscribers:
                events.put(data)

    def __apply(self, operation: dict) -> None:
        """ What an operation changes: the conversation shown (add, patch, append, remove, reset) or the state """
        match operation["type"]:
            case "add":
                item: dict = dict(operation["item"])
                self.__log.append(item)
                self.__items[item["id"]] = item
            case "patch":
                self.__items[operation["id"]].update(operation["item"])
            case "append":
                self.__items[operation["id"]]["text"] += operation["text"]
            case "remove":
                self.__log.remove(self.__items.pop(operation["id"]))
            case "reset":
                self.__log = [dict(item) for item in operation["log"]]
                self.__items = {item["id"]: item for item in self.__log}
            case "state":
                self.__state.update(operation["state"])

    def __add(self, **item) -> int:
        """ Show a new item at the end of the conversation, and get its id """
        item["id"] = next(self.__ids)
        self.__emit({"type": "add", "item": item})
        return item["id"]

    def __patch(self, identifier: int, **fields) -> None:
        self.__emit({"type": "patch", "id": identifier, "item": fields})

    def __set(self, **state) -> None:
        self.__emit({"type": "state", "state": state})

    def __notice(self, text: str, tone: str = "info", **extra) -> int:
        """ A line of Louis itself, not of the model: tone is info, success, warn, error or guard """
        return self.__add(kind="notice", text=text, tone=tone, **extra)

    def __card(self, title: str, rows: list[dict], foot: str | None = None) -> int:
        """ A list (sessions, links, schemas...): a row has a text, a meta, and may send a command or fill the input """
        return self.__add(kind="card", title=title, rows=rows, foot=foot)

    def __reset(self, items: list[dict]) -> None:
        """ Another session: its conversation in place of the one shown """
        self.__text = self.__thinking = self.__progress = None
        self.__running = []
        self.__emit({"type": "reset", "log": [{**item, "id": next(self.__ids)} for item in items]})

    def __close_thinking(self) -> None:
        """ The model stopped thinking: it writes, or calls a tool """
        if self.__thinking is not None:
            self.__patch(self.__thinking, done=True)
            self.__thinking = None

    def __close_text(self) -> None:
        """ A reply cut short (Stop, an error): what was written of it stays, laid out """
        if self.__text is None:
            return
        text: str = self.__items[self.__text]["text"]
        if text.strip():
            self.__patch(self.__text, done=True, html=markdown(text))
        else:
            self.__emit({"type": "remove", "id": self.__text})
        self.__text = None

    # ---------- The events of the app, on its thread ----------

    def __on_any(self, event: Event) -> None:
        """ The app reacts to the message taken: from now on, the Stop button cancels it as Ctrl+C does """
        if self.__working:
            self.__interruptible = True

    def __on_stop(self, signum, frame) -> None:
        """ The Stop button of a page: ignored once the app is done, so it never stops Louis itself """
        if self.__interruptible:
            raise KeyboardInterrupt

    def __on_started(self, event: Event) -> None:
        self.__set(model=event.data["model"], think=event.data["think"], commands=event.data["commands"])

    def __on_session_created(self, event: Event) -> None:
        """ A new session, empty: the pages start over """
        self.__always.clear()
        self.__reset([])
        self.__set(user=event.data["user"], persistent=event.data["persistent"], session=None)
        if event.data["custom_prompt"]:
            self.__notice("Nouvelle session avec ton prompt système.")

    def __on_session_saved(self, event: Event) -> None:
        """ The session is in the database from its first message on: at the top of the sidebar """
        identifier: int = event.data["id"]
        entry: dict = {"id": identifier, "title": self.__question.strip().split("\n", 1)[0] or "(vide)",
                       "created_at": now(), "here": True, "cwd": short_path(os.getcwd())}
        others: list[dict] = [session for session in self.__state["sessions"] if session["id"] != identifier]
        self.__set(session=identifier, sessions=[entry] + others)

    def __on_session_resumed(self, event: Event) -> None:
        """ The session resumed, shown whole """
        self.__always.clear()
        items: list[dict] = history_items(event.data.get("history") or [])
        items.append({"kind": "notice", "tone": "info",
                      "text": f"Session #{event.data['id']} reprise ({plural(event.data['messages'], 'message')})."})
        self.__reset(items)
        self.__set(session=event.data["id"])

    def __on_session_list(self, event: Event) -> None:
        """ The sidebar, and the list in the conversation when the user asked for it """
        self.__set(sessions=sidebar(event.data["sessions"]))
        if self.__quiet:
            return
        if not event.data["sessions"]:
            self.__notice(f"Aucune session enregistrée pour {event.data['user']} : une session l'est dès ton premier "
                          "message.")
            return
        rows: list[dict] = []
        for session in event.data["sessions"]:
            where: str = "" if session["here"] else f" · {short_path(session['cwd'])}"
            row: dict = {"text": one_line(session["first_message"] or "(vide)"),
                         "meta": f"#{session['id']} · {local(session['created_at'])}{where}", "current": session["current"]}
            if session["here"] and not session["current"]:
                row["command"] = f"/resume {session['id']}"
            rows.append(row)
        self.__card(f"Sessions de {event.data['user']}", rows,
                    "Clique sur une session pour la reprendre (celles d'un autre dossier se reprennent depuis lui).")

    def __on_turn_started(self, event: Event) -> None:
        """ The model answers: unlike a command (/think...), the pages show Louis at work until the turn ends """
        self.__text = self.__thinking = None
        self.__running = []
        self.__set(turn=True)

    def __on_thinking(self, event: Event) -> None:
        """ What the model thinks before replying (/think), as it comes """
        if self.__thinking is None:
            self.__thinking = self.__add(kind="thinking", text="", done=False)
        self.__emit({"type": "append", "id": self.__thinking, "text": event.data["text"]})

    def __on_text(self, event: Event) -> None:
        """ A piece of the reply, as the model writes it """
        self.__close_thinking()
        if self.__text is None:
            self.__text = self.__add(kind="text", text="", done=False)
        self.__emit({"type": "append", "id": self.__text, "text": event.data["text"]})

    def __on_reply(self, event: Event) -> None:
        """ The reply is whole: laid out by the server, so a page without its Markdown library shows it too """
        self.__close_thinking()
        content: str = event.data["content"]
        if self.__text is not None and content.strip():
            self.__patch(self.__text, text=content, html=markdown(content), done=True)
        elif self.__text is not None:
            self.__emit({"type": "remove", "id": self.__text})
        elif content.strip():
            self.__add(kind="text", text=content, html=markdown(content), done=True)
        self.__text = None

    def __on_turn_ended(self, event: Event) -> None:
        """ What was left open is closed, and why the turn stopped, unless it is done """
        self.__close_thinking()
        self.__close_text()
        for identifier, _ in self.__running:
            self.__patch(identifier, status="cancelled")
        self.__running = []
        self.__set(turn=False)
        match event.data["reason"]:
            case "done":
                pass
            case "cancelled":
                self.__notice("Réponse interrompue.")
            case "error":
                self.__notice(f"Erreur : {event.data['message']}", "error")
            case _:
                self.__notice(event.data["message"] or "La réponse s'est arrêtée.", "warn")

    def __on_context(self, event: Event) -> None:
        self.__set(context={"used": event.data["used"], "size": event.data["size"]})

    def __on_compacted(self, event: Event) -> None:
        """ The model sees less of the conversation: the user knows why it may read a file again """
        parts: list[str] = []
        if event.data["results"]:
            parts.append(f"{event.data['results']} anciens résultats d'outils réduits à leurs premières lignes")
        if event.data["dropped"]:
            parts.append(f"{event.data['dropped']} anciens messages mis de côté")
        self.__notice(f"Contexte allégé : {', '.join(parts)}.")

    def __on_structured(self, event: Event) -> None:
        """ The JSON of a reply that matches its schema. One that does not is told by the end of the turn """
        if not event.data["valid"]:
            return
        text: str = f"```json\n{json.dumps(event.data['data'], ensure_ascii=False, indent=2)}\n```"
        attempts: int = event.data["attempts"]
        self.__add(kind="text", text=text, html=markdown(text), done=True,
                   meta=f"schéma {event.data['schema']}{f', {attempts} essais' if attempts > 1 else ''}")

    def __on_tool_started(self, event: Event) -> None:
        self.__close_thinking()
        identifier: int = self.__add(**tool_item(event.data["name"], event.data["arguments"], event.data["producer"]))
        self.__running.append((identifier, event.data["name"]))

    def __on_tool_ended(self, event: Event) -> None:
        """ The last call of this tool still running: what it gave """
        name: str = event.data["name"]
        found: tuple[int, str] | None = next((call for call in reversed(self.__running) if call[1] == name), None)
        if found is None:
            return
        self.__running.remove(found)
        self.__patch(found[0], **tool_result(name, event.data["result"], event.data["ok"], event.data["duration"]))

    def __on_permission(self, event: Event) -> None:
        """
            Ask the pages, and wait for one of them to answer: the bus is synchronous, the app waits too. Stop or
            Ctrl+C meanwhile cancels the turn, the tool never acts
        """
        data: dict = event.data
        tool: str = data["tool"]
        every_time: bool = bool(data.get("every_time"))
        item: dict = {"kind": "permission", "tool": tool, "summary": data["summary"], "every_time": every_time,
                      "preview": data.get("preview") or "", "request": data["id"]}
        if not every_time and tool in self.__always:
            self.__add(**item, status="auto")
            self.__bus.dispatch(TOOL_GRANT_PERMISSION, id=data["id"], granted=True)
            return
        self.__close_thinking()
        identifier: int = self.__add(**item, status="pending")
        with self.__lock:
            # An answer that came too late for a request cancelled meanwhile is not the one to this one
            while not self.__answers.empty():
                self.__answers.get_nowait()
            self.__asking = data["id"]
            self.__emit({"type": "state", "state": {"asking": True}})
        status: str = "cancelled"
        try:
            choice: str = self.__answers.get()
            if every_time and choice == "a":
                choice = "y"
            if choice == "a":
                self.__always.add(tool)
            status = {"y": "granted", "a": "always"}.get(choice, "refused")
        finally:
            with self.__lock:
                self.__asking = None
            self.__set(asking=False)
            self.__patch(identifier, status=status)
        self.__bus.dispatch(TOOL_GRANT_PERMISSION, id=data["id"], granted=status in ("granted", "always"))

    def __on_guard(self, event: Event) -> None:
        """ What the guard changed, before the reply or the refusal """
        data: dict = event.data
        if data["stage"] == "tool_call":
            text = f"Appel bloqué par le garde-fou ({', '.join(data['rails'])})"
        elif data["stage"] == "tool_result":
            text = "Résultat filtré par le garde-fou (passages piégés retirés, données sensibles masquées)"
        elif data["action"] == "refused":
            what: str = "Message bloqué" if data["stage"] == "input" else "Réponse bloquée"
            text = f"{what} par le garde-fou ({', '.join(data['rails'])})"
        elif data["stage"] == "input":
            text = f"Message anonymisé avant le modèle : {one_line(data['content'])}"
        else:
            text = "Réponse anonymisée par le garde-fou"
        self.__notice(text, "guard")

    def __on_thinking_switched(self, event: Event) -> None:
        enabled: bool = event.name == THINKING_ENABLED
        self.__set(think=enabled)
        self.__notice("Réflexion activée : Louis réfléchit avant chaque réponse, c'est plus long." if enabled
                      else "Réflexion désactivée : Louis répond directement.")

    def __on_export_done(self, event: Event) -> None:
        """ ✓ Session #12 exportée en JSON (8 messages) : ~/projet/exports/session-12.json """
        data: dict = event.data
        which: str = f"session #{data['id']}" if data["id"] is not None else "session"
        shown: str = {"md": "Markdown"}.get(data["format"], data["format"].upper())
        files: list[str] | None = data.get("files")
        if files:
            what: str = files[0] if len(files) == 1 else f"{len(files)} fichiers"
            text: str = f"{what} ({which}) exporté{'s' if len(files) > 1 else ''} en {shown}"
        else:
            written: str = f", {plural(data['artifacts'], 'fichier')}" if data.get("artifacts") else ""
            text = f"{which.capitalize()} exportée en {shown} ({plural(data['messages'], 'message')}{written})"
        self.__notice(f"{text} : {home(data['path'])}", "success")

    def __on_share_created(self, event: Event) -> None:
        """ The public link, to open or copy, and how to close it """
        data: dict = event.data
        what: str = (f"de {data['title']} (session #{data['id']})" if data["kind"] == "artifact"
                     else f"de la session #{data['id']}")
        foot: list[str] = []
        if data["masked"]:
            foot.append(f"{plural(data['masked'], 'texte')} masqué{'s' if data['masked'] > 1 else ''} "
                        "(données sensibles).")
        foot.append(f"/unshare {data['token'][:8]} pour le fermer.")
        self.__notice(f"Lien public {what} :", "success", href=data["url"], foot=" ".join(foot))

    def __on_share_list(self, event: Event) -> None:
        if not event.data["shares"]:
            self.__notice(f"Aucun lien public ouvert pour {event.data['user']} : /share pour en créer un.")
            return
        rows: list[dict] = []
        for share in event.data["shares"]:
            session: str = f"session #{share['session_id']}" if share["session_id"] is not None else "session supprimée"
            rows.append({"text": share["title"] or "(sans titre)", "href": share["url"],
                         "meta": f"{share['token'][:8]} · {session} · {local(share['created_at'])}",
                         "action": {"label": "Fermer", "command": f"/unshare {share['token'][:8]}"}})
        self.__card(f"Liens publics de {event.data['user']}", rows)

    def __on_schema_list(self, event: Event) -> None:
        folder: str = short_path(event.data["folder"])
        if not event.data["schemas"]:
            self.__notice(f"Aucun schéma : ajoutes-en dans {folder}/ (un fichier <nom>.json par schéma).")
            return
        rows: list[dict] = [{
            "text": schema["name"], "warn": not schema["ok"], "fill": f"/json {schema['name']} ",
            "meta": (schema["description"] or "") + (" (projet)" if schema["origin"] == "projet" else ""),
        } for schema in event.data["schemas"]]
        self.__card("Schémas de /json <schéma> <question>", rows,
                    f"Les tiens vont dans {folder}/, ils passent avant ceux de Louis du même nom.")

    def __on_command_unknown(self, event: Event) -> None:
        rows: list[dict] = [{
            "text": f"/{command['name']} {command['usage']}".strip(), "meta": command["description"],
            "fill": f"/{command['name']}{' ' if command['usage'] else ''}",
        } for command in event.data["commands"]]
        self.__card(f"Commande inconnue : /{event.data['name']}. Les commandes sont :", rows)

    def __on_command_error(self, event: Event) -> None:
        if not self.__quiet:
            self.__notice(home(event.data["message"]), "error")

    def __on_rag_indexing(self, event: Event) -> None:
        """ A folder being read: embedding a big one takes minutes """
        self.__progress = self.__add(
            kind="progress", text=f"Indexation de {short_path(event.data['root'])} ({plural(event.data['files'], 'fichier')})…",
            detail="", value=0.0, done=False
        )

    def __on_rag_progress(self, event: Event) -> None:
        if self.__progress is None:
            return
        data: dict = event.data
        if event.name == RAG_INDEX_PROGRESS:
            self.__patch(self.__progress, detail=f"{data['done']}/{data['total']} fichiers",
                         value=data["done"] / data["total"] if data["total"] else 1.0)
        else:
            self.__patch(self.__progress, detail=f"{short_path(data['path'])} décrit ({data['described']} passages "
                                                 f"décrits, {data['reused']} repris, {data['seconds']:.0f}s)")

    def __on_rag_indexed(self, event: Event) -> None:
        """ What the folder gave: its files, its passages, and if the search by meaning works on them """
        data: dict = event.data
        text: str = (f"Source « {data['source']} » à jour : {plural(data['files'], 'fichier')} ({data['updated']} lus, "
                     f"{data['unchanged']} inchangés, {data['removed']} retirés, {data['skipped']} ignorés), "
                     f"{plural(data['chunks'], 'passage')} · {data['duration']:.1f}s")
        notes: list[str] = []
        if data["chunks"] and data["embedded"] < data["chunks"]:
            notes.append(f"Recherche par mots-clés seulement pour {data['chunks'] - data['embedded']} passages : "
                         f"{data['warning'] or "aucun modèle d'embedding"}. Relance /index quand il répond.")
        if data.get("excluded"):
            notes.append(f"{data['excluded']} fichiers exclus par {', '.join(data['exclude'])}.")
        if data.get("describe"):
            notes.append(f"Code décrit : {data['described']} passages par le modèle ({data['describe_seconds']:.0f}s), "
                         f"{data['reused']} repris des descriptions déjà faites.")
            if data.get("describe_warning"):
                notes.append(f"Le reste sans description : {data['describe_warning']}. Relance /index quand il répond.")
        made: list[dict] = data.get("generated") or []
        if made:
            shown: str = ", ".join(item["path"] for item in made[:5]) + (f" et {len(made) - 5} autres" if len(made) > 5 else "")
            notes.append(f"Laissés de côté, générés par un programme ({len(made)}) : {shown}. Pour en garder : réglage "
                         "rag.index.generated_ratio.")
        if self.__progress is not None:
            self.__patch(self.__progress, text=text, detail="\n".join(notes), value=1.0, done=True)
            self.__progress = None
        else:
            self.__notice(text, "success", foot="\n".join(notes) or None)

    def __on_rag_sources(self, event: Event) -> None:
        sources: list[dict] = event.data["sources"]
        if not sources:
            self.__notice("La base de connaissances est vide : /index <dossier> y met de la documentation ou du code.")
            return
        rows: list[dict] = []
        for source in sources:
            flags: list[str] = []
            if source["embedded"] != source["chunks"]:
                flags.append("mots-clés seulement")
            if source.get("describe"):
                flags.append("code décrit")
            if source.get("exclude"):
                flags.append(f"sans {', '.join(source['exclude'])}")
            rows.append({"text": source["name"], "meta": " · ".join(
                [plural(source["files"], "fichier"), plural(source["chunks"], "passage"), short_path(source["root"])]
                + flags
            )})
        self.__card(f"Base de connaissances ({plural(len(sources), 'source')})", rows)

class _Server(ThreadingHTTPServer):
    """ The server of the pages, on IPv4 or IPv6 as its address asks """
    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler) -> None:
        self.address_family = socket.AF_INET6 if ":" in address[0] else socket.AF_INET
        super().__init__(address, handler)

class _Handler(BaseHTTPRequestHandler):
    """ One request of a page: the chat page, its events, what it sends, or a public link """
    server_version = "Louis"
    sys_version = ""

    def __init__(self, *args, web: WebInterface, **kwargs) -> None:
        self.__web: WebInterface = web
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args) -> None:
        """ In the log, not in the terminal """
        log.debug(f"[web] {self.address_string()} {format % args}")

    def do_GET(self) -> None:
        path: str = urlsplit(self.path).path
        if path.startswith("/s/"):
            # Public, and reached by the address the links give (a proxy...): no check of the host
            self.__share(path.removeprefix("/s/"))
        elif not self.__trusted():
            self.__json(403, {"error": "Adresse refusée."})
        elif path == "/":
            self.__page()
        elif path == "/api/events":
            self.__events()
        else:
            self.__json(404, {"error": "Introuvable."})

    def do_POST(self) -> None:
        path: str = urlsplit(self.path).path
        # JSON only: another site can not send it here without asking the browser first (CORS), which is refused
        if not self.__trusted() or not self.__same_origin():
            self.__json(403, {"error": "Adresse refusée."})
            return
        if self.headers.get_content_type() != "application/json":
            self.__json(415, {"error": "JSON seulement."})
            return
        body: dict | None = self.__body()
        if body is None:
            self.__json(400, {"error": "Requête invalide."})
        elif path == "/api/messages":
            self.__message(body)
        elif path == "/api/permission":
            self.__permission(body)
        elif path == "/api/stop":
            if self.__web.stop():
                self.__json(202, {})
            else:
                self.__json(409, {"error": "Louis ne fait rien en ce moment."})
        else:
            self.__json(404, {"error": "Introuvable."})

    def __trusted(self) -> bool:
        """ A page of this computer, by one of its names: a site whose name now leads here is refused (DNS rebinding) """
        names: frozenset[str] | None = self.__web.names
        if names is None:
            return True
        host: str | None = urlsplit(f"//{self.headers.get('Host', '')}").hostname
        return host is not None and host.lower() in names

    def __same_origin(self) -> bool:
        """ Sent by a page of Louis, or by something that is no page at all (curl) """
        origin: str | None = self.headers.get("Origin")
        return origin is None or urlsplit(origin).netloc.lower() == (self.headers.get("Host") or "").lower()

    def __body(self) -> dict | None:
        """ The JSON object sent, None if it is not one """
        try:
            length: int = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= MAX_BODY:
                return None
            body = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            return None
        return body if isinstance(body, dict) else None

    def __message(self, body: dict) -> None:
        text, shown = body.get("text"), body.get("shown", True)
        if not isinstance(text, str) or not text.strip() or not isinstance(shown, bool):
            self.__json(400, {"error": "Message vide."})
            return
        refused: str | None = self.__web.submit(text, shown)
        self.__json(409 if refused else 202, {"error": refused} if refused else {})

    def __permission(self, body: dict) -> None:
        request, choice = body.get("id"), body.get("choice")
        if not isinstance(request, int) or isinstance(request, bool) or choice not in CHOICES:
            self.__json(400, {"error": "Réponse invalide."})
        elif self.__web.answer(request, choice):
            self.__json(202, {})
        else:
            self.__json(409, {"error": "Cette demande n'attend plus de réponse."})

    def __page(self) -> None:
        """ The chat page, read at each request """
        self.__send(200, PAGE.read_bytes(), "text/html; charset=utf-8", PAGE_POLICY)

    def __share(self, token: str) -> None:
        """ The page of a public link, as /export --html writes it: 404 for a link that does not exist or was closed """
        document: dict | None = self.__web.shared(token) if TOKEN.fullmatch(token) else None
        if document is None:
            self.__send(404, NOT_FOUND.encode(), "text/html; charset=utf-8", SHARE_POLICY)
            return
        try:
            page: bytes = render(document).encode()
        except Exception:
            log.exception(f"[web] the share {token[:6]}… could not be laid out")
            self.__send(500, NOT_FOUND.encode(), "text/html; charset=utf-8", SHARE_POLICY)
            return
        self.__send(200, page, "text/html; charset=utf-8", SHARE_POLICY)

    def __events(self) -> None:
        """ What the page shows, then each change as it comes (Server-Sent Events), until it leaves or Louis stops """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        events: queue.Queue = self.__web.subscribe()
        try:
            while True:
                try:
                    data: str | None = events.get(timeout=KEEPALIVE)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                if data is None:
                    break
                self.wfile.write(f"data: {data}\n\n".encode())
                self.wfile.flush()
        except OSError:
            pass
        finally:
            self.__web.unsubscribe(events)

    def __json(self, status: int, data: dict) -> None:
        self.__send(status, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def __send(self, status: int, body: bytes, content_type: str, policy: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if policy is not None:
            self.send_header("Content-Security-Policy", policy)
        self.end_headers()
        self.wfile.write(body)
