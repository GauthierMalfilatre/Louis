##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Scribe: beside the chat, a small model writes the title and the summary of each session, and welcomes a new one
##
## It works in a thread of its own, on the CPU, with its own connection to the database: a reply never waits for it,
## and it never takes the GPU from the chat model. What it wrote is told to the bus from its thread (SESSION_DESCRIBED,
## APP_WELCOME): the web page shows it, a terminal never draws from another thread
##
from config.prompt import NUDGE_PROMPT, EMPTY_PROMPT, REVISE_PROMPT
from events.event_bus import EventBus
from events.event import Event
from events.event_list import CHAT_TURN_ENDED, SESSION_CREATED, SESSION_SAVED, SESSION_RESUMED
from events.event_list import SESSION_DESCRIBED, APP_WELCOME
from logger.logger import log
from rag.embedder import Embedder, EmbedError
from session.database import Database, now
from session.message import Message
from tool.tool import failed
from utils.project import project
from datetime import datetime
import json
import numpy as np
import os
import queue
import re
import requests
import threading

# What it is asked. The title says what was done together: the last request of a session is often a cancelled one
DESCRIBE: str = (
    "Tu tiens le carnet de Louis, un assistant de code. Pour la conversation donnée, écris « title » : 3 à 6 mots sur le "
    "travail principal fait ensemble (ce qui a vraiment été fait, pas une demande interrompue), sans guillemets ni "
    "point ; et « summary » : une phrase de moins de 25 mots qui dit où on en est, en tutoyant l'utilisateur (« Tu as "
    "ajouté… »). En français."
)
# The greeting is the page's (by the hour, with the name of the user): the model only writes the sentence under it. Asked
# for both, small models greet "Bonjour" at 18h and misspell the name
WELCOME: str = (
    "Tu es Louis, un assistant de code chaleureux et sobre. L'utilisateur ouvre une nouvelle session ; la salutation est "
    "déjà écrite. Écris « lead » : une seule phrase de moins de 18 mots, en le tutoyant, qui propose une suite concrète "
    "à partir de sa dernière session ou de ses fichiers modifiés. Ne parle pas de l'heure, ne le salue pas, pas d'emoji. "
    "En français."
)
DESCRIBED: dict = {"type": "object", "properties": {"title": {"type": "string"}, "summary": {"type": "string"}},
                   "required": ["title", "summary"]}
WELCOMED : dict = {"type": "object", "properties": {"lead": {"type": "string"}}, "required": ["lead"]}

# What is kept of what it writes, on one line
TITLE_CHARS  : int = 60
SUMMARY_CHARS: int = 220
LEAD_CHARS   : int = 160
# What it reads of a session: each message cut to MESSAGE_CHARS, and the whole to TRANSCRIPT_CHARS, its start (what it
# was about) and its end (where it is). A small model on the CPU reads ~100 tokens a second
MESSAGE_CHARS   : int = 300
TRANSCRIPT_CHARS: int = 3500
TRANSCRIPT_START: int = 800
# Seconds without a job before the scribe describes a session of before it, the newest first: the older sessions get
# their title and their vector (for /find) when nothing else is asked, once each
IDLE: float = 3.0
DAYS: list[str] = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

class ScribeError(Exception):
    """ The model of the scribe did not answer: Ollama is stopped, the model is not downloaded, or it wrote no JSON """
    def __init__(self, message: str):
        super().__init__(message)
        self.message: str = message

def one_line(text: object, most: int) -> str:
    """ What the model wrote, on one line: without the quotes and the markup it adds, cut to most characters """
    line: str = " ".join(re.sub(r"[*`#]+", "", str(text or "")).split()).strip(" \"'«»“”")
    return line if len(line) <= most else line[:most - 1].rstrip() + "…"

def asks(message: Message) -> bool:
    """ A message of the user, not one Louis sent in its name (the nudge, the empty reply, the problems of a draft) """
    return (message.role == "user" and message.content != NUDGE_PROMPT
            and not message.content.startswith(EMPTY_PROMPT.split("{")[0])
            and not message.content.startswith(REVISE_PROMPT.split("{")[0]))

def transcript(messages: list[Message]) -> str:
    """
        A session as the scribe reads it: what the user asked, the start of what Louis answered, the tools it used, never
        their results. A request left without an answer is told so (cancelled, it is not what the session is about)
    """
    lines: list[str] = []
    # The calls of the last reply not answered yet: where their line is, to tell if they failed (a write refused)
    pending: list[tuple[int, str]] = []
    for i, message in enumerate(messages):
        content: str = " ".join((message.content or "").split())
        short: str = content if len(content) <= MESSAGE_CHARS else content[:MESSAGE_CHARS - 1] + "…"
        if asks(message):
            following: list[Message] = []
            for later in messages[i + 1:]:
                if asks(later):
                    break
                following.append(later)
            answered: bool = any(later.role == "assistant" and (later.content.strip() or later.tool_calls)
                                 for later in following)
            lines.append(f"Utilisateur : {short}" + ("" if answered else "\n(interrompu, sans réponse)"))
        elif message.role == "assistant":
            if short:
                lines.append(f"Louis : {short}")
            pending = []
            for call in message.tool_calls or []:
                target = call.arguments.get("path") or call.arguments.get("query") or call.arguments.get("action")
                what: str = f"{call.name}{f' sur {target}' if target else ''}"
                pending.append((len(lines), what))
                lines.append(f"[Louis a utilisé {what}]")
        elif message.role == "tool" and pending:
            line, what = pending.pop(0)
            if content.startswith("Refusé"):
                lines[line] = f"[Louis a voulu utiliser {what} : l'utilisateur a refusé, rien n'a été fait]"
            elif failed(content):
                lines[line] = f"[Louis a voulu utiliser {what} : échec, rien n'a été fait]"
    text: str = "\n".join(lines)
    if len(text) <= TRANSCRIPT_CHARS:
        return text
    return f"{text[:TRANSCRIPT_START]}\n[…]\n{text[-(TRANSCRIPT_CHARS - TRANSCRIPT_START):]}"

def described(title: str, summary: str, first: str | None) -> str:
    """ What a session is searched by (/find): its title, its summary, and its first request """
    return "\n".join(part for part in (title, summary, first or "") if part)

def packed(vector: list[float]) -> bytes:
    """ A vector as the database keeps it: float32, of length 1, so that a dot product is its cosine """
    array: np.ndarray = np.asarray(vector, dtype=np.float32)
    norm: float = float(np.linalg.norm(array))
    return (array / norm if norm else array).tobytes()

class Scribe:
    """
        The scribe of a user: once a reply is done, the title, the summary and the vector of its session (when the user
        is saved), and when a session starts, the sentence that welcomes the user. One request at a time, in its thread:
        the jobs asked meanwhile for the same session are done once
    """
    def __init__(self, settings: dict, bus: EventBus, database: str | None, user_id: int | None, welcome: bool = True):
        """
            Start the scribe of the user: database is the path of its database, None for the anonymous user (nothing to
            describe then). welcome: a new session is welcomed (an interface shows it)
        """
        self.__uri      : str        = settings["chat.uri"]
        self.__model    : str        = settings["scribe.model"]
        self.__gpu      : bool       = bool(settings.get("scribe.gpu", False))
        self.__keepalive: str        = settings.get("scribe.keepalive", "30m")
        self.__context  : int        = int(settings.get("scribe.context", 4096))
        self.__bus      : EventBus   = bus
        self.__database : str | None = database
        self.__user     : int | None = user_id
        self.__welcomes : bool       = welcome
        self.__embedder : Embedder | None = embedder(settings)
        # The session being talked in (None until its first message is saved), and the welcome asked last: an older one
        # that comes late is not shown
        self.__session  : int | None = None
        self.__welcome  : int        = 0
        self.__jobs     : queue.Queue = queue.Queue()
        self.__waiting  : set[int]    = set()
        # The sessions of before not described yet are looked for until there are no more; those it could not describe
        # (nothing asked in them) are not tried again
        self.__backlog  : bool        = database is not None
        self.__tried    : set[int]    = set()
        self.__lock     : threading.Lock = threading.Lock()
        bus.subscribe(self.__on_session, SESSION_CREATED, SESSION_SAVED, SESSION_RESUMED)
        bus.subscribe(self.__on_turn_ended, CHAT_TURN_ENDED)
        threading.Thread(target=self.__work, name="louis-scribe", daemon=True).start()
        log.info(f"[scribe] {self.__model} on the {'GPU' if self.__gpu else 'CPU'}")

    def __on_session(self, event: Event) -> None:
        """ Another session: a new one is welcomed """
        self.__session = None if event.name == SESSION_CREATED else event.data["id"]
        if event.name == SESSION_CREATED and self.__welcomes:
            with self.__lock:
                self.__welcome += 1
                self.__jobs.put(("welcome", self.__welcome))

    def __on_turn_ended(self, event: Event) -> None:
        """ A reply is done: its session is described again, once even if several replies end meanwhile """
        if self.__session is None or self.__database is None:
            return
        with self.__lock:
            if self.__session in self.__waiting:
                return
            self.__waiting.add(self.__session)
        self.__jobs.put(("describe", self.__session))

    def __work(self) -> None:
        """ The thread of the scribe: its own connection (a connection of sqlite stays in its thread), one job at a time """
        db: Database | None = Database(self.__database) if self.__database else None
        while True:
            try:
                kind, value = self.__jobs.get(timeout=IDLE if self.__backlog else None)
            except queue.Empty:
                value = self.__undescribed(db)
                if value is None:
                    self.__backlog = False
                    continue
                kind = "describe"
            try:
                if kind == "describe":
                    with self.__lock:
                        self.__waiting.discard(value)
                    self.__describe(db, value)
                else:
                    self.__welcome_user(db, value)
            except ScribeError as e:
                log.warning(f"[scribe] {kind}: {e.message}")
            except Exception:
                log.exception(f"[scribe] {kind} failed")

    def __undescribed(self, db: Database) -> int | None:
        """ The newest session of the user without a title, not tried yet: None when they all have one """
        for row in db.fetchall("SELECT id FROM sessions WHERE user_id = ? AND title IS NULL ORDER BY id DESC", (self.__user,)):
            if row["id"] not in self.__tried and row["id"] != self.__session:
                self.__tried.add(row["id"])
                return row["id"]
        return None

    def __describe(self, db: Database, session_id: int) -> None:
        """ The title, the summary and the vector of a session, saved, then told """
        messages: list[Message] = [Message.from_row(row) for row in db.fetchall(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
        )]
        text: str = transcript(messages)
        if not text:
            return
        answer: dict = self.__ask(DESCRIBE, text, DESCRIBED)
        title, summary = one_line(answer.get("title"), TITLE_CHARS).rstrip("."), one_line(answer.get("summary"), SUMMARY_CHARS)
        if not title:
            raise ScribeError(f"{self.__model} n'a pas donné de titre")
        first: str | None = next((message.content for message in messages if asks(message)), None)
        vector: bytes | None = None
        if self.__embedder is not None:
            try:
                vector = packed(self.__embedder.documents([described(title, summary, first)], gpu=False)[0])
            except EmbedError as e:
                log.warning(f"[scribe] session #{session_id} not embedded: {e.message}")
        db.execute("UPDATE sessions SET title = ?, summary = ?, vector = ?, described_at = ? WHERE id = ?",
                   (title, summary, vector, now(), session_id))
        log.info(f"[scribe] session #{session_id}: {title} | {summary}")
        self.__bus.dispatch(SESSION_DESCRIBED, id=session_id, title=title, summary=summary)

    def __welcome_user(self, db: Database | None, asked: int) -> None:
        """ A sentence for a new session, from the last one held in this folder and the files changed: none without them """
        cwd: str = os.getcwd()
        hints: dict = project(cwd)
        last = db.fetchone(
            "SELECT title, summary FROM sessions WHERE user_id = ? AND cwd = ? AND title IS NOT NULL ORDER BY id DESC LIMIT 1",
            (self.__user, cwd)
        ) if db is not None and self.__user is not None else None
        if last is None and not hints["changed"]:
            return
        moment: datetime = datetime.now()
        lines: list[str] = [f"Jour : {DAYS[moment.weekday()]}", f"Projet : {hints['name']}"]
        if last is not None:
            lines.append(f"Dernière session : « {last['title']} » — {last['summary']}")
        lines.append(f"Fichiers modifiés dans git : {', '.join(hints['changed']) or 'aucun'}")
        lead: str = one_line(self.__ask(WELCOME, "\n".join(lines), WELCOMED).get("lead"), LEAD_CHARS)
        # Another session started meanwhile: this sentence is not about it
        if lead and asked == self.__welcome:
            self.__bus.dispatch(APP_WELCOME, lead=lead)

    def __ask(self, system: str, prompt: str, schema: dict) -> dict:
        """ One request to the model of the scribe, its answer as the JSON the schema asks. NOTE: Raisable (ScribeError) """
        try:
            res = requests.post(f"{self.__uri}/api/chat", timeout=(5.0, 300.0), json={
                "model": self.__model,
                "stream": False,
                "think": False,
                "format": schema,
                "keep_alive": self.__keepalive,
                # num_gpu 0: on the CPU, the chat model keeps the whole GPU
                "options": {"num_ctx": self.__context, "num_predict": 160, "temperature": 0.3,
                            **({} if self.__gpu else {"num_gpu": 0})},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            })
        except requests.RequestException as e:
            raise ScribeError(f"Ollama ne répond pas à {self.__uri} ({type(e).__name__})") from e
        if res.status_code == 404:
            raise ScribeError(f"le modèle {self.__model} n'est pas téléchargé : ollama pull {self.__model}")
        if res.status_code != 200:
            raise ScribeError(f"Ollama a refusé la requête à {self.__model} ({res.status_code})")
        try:
            answer = json.loads((res.json().get("message") or {}).get("content") or "")
        except ValueError as e:
            raise ScribeError(f"{self.__model} n'a pas répondu en JSON") from e
        if not isinstance(answer, dict):
            raise ScribeError(f"{self.__model} n'a pas répondu par un objet JSON")
        return answer

def embedder(settings: dict) -> Embedder | None:
    """ The embedding model of the knowledge base, on the CPU, for the sessions: None without one """
    model: str | None = settings.get("rag.embed.model")
    if not model:
        return None
    return Embedder(settings["chat.uri"], model, settings.get("rag.embed.query_prefix", ""),
                    settings.get("rag.embed.document_prefix", ""), gpu=False)
