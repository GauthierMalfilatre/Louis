##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## App Class (the manager)
##

from interface.interface import Interface
from model.model import OllamaModel
from model.model_exception import ModelException
from model.reply import Reply
from tool.tool_manager import ToolManager
from tool.tool import Tool, failed
from tool.tool_call import ToolCall
from tool.impl.file.tool_tree import TreeTool
from tool.impl.file.tool_cat import CatTool
from tool.impl.file.tool_edit import EditTool
from tool.impl.file.tool_write import WriteTool
from tool.impl.file.tool_search import SearchTool
from tool.impl.file.tool_mkdir import MkdirTool
from tool.impl.web.tool_websearch import InternetTool
from tool.impl.git.tool_git import GitTool
from tool.impl.git.tool_pr import PullRequestTool
from tool.impl.exec.tool_run import RunTool, available as sandbox_available
from tool.impl.rag.tool_knowledge import KnowledgeTool
from tool.permission import PermissionManager
from rag.knowledge import Knowledge
from guard.guard import Guard
from guard.verdict import Verdict
from tool.seen_files import SeenFiles
from app.context_window import ContextWindow, capped, share, MAX_RESULT, ROUND, CHARS_PER_TOKEN
from events.event_bus import EventBus, Event
from events.event_list import *
from logger.logger import log, log_event
from config.prompt import NUDGE_PROMPT, EMPTY_PROMPT, SUMMARY_PROMPT, MERGE_PROMPT, VERIFY_PROMPT, REACT_PROMPT, REVISE_PROMPT
from session.user import User
from session.session import Session
from session.scribe import Scribe
from command.command import CommandTree
from command.impl.command_clear import ClearCommand
from command.impl.command_think import ToggleThinkCommand
from command.impl.command_sessions import SessionsCommand
from command.impl.command_resume import ResumeCommand
from command.impl.command_json import JsonCommand
from command.impl.command_schemas import SchemasCommand
from structured.reply import instruction, checked, retry, shown
from command.impl.command_export import ExportCommand
from command.impl.command_share import ShareCommand
from command.impl.command_shares import SharesCommand
from command.impl.command_unshare import UnshareCommand
from command.impl.command_index import IndexCommand, UnindexCommand
from command.impl.command_find import FindCommand
from monitor.recorder import Recorder
from collections import Counter
from collections.abc import Callable
from typing import Any
from dataclasses import asdict
from datetime import date
import json
import os
import re
import time

# A reply that says what the model is about to do, in French or English. In French, "je vais" must lead to
# a verb ("je vais créer", "je vais d'abord lire"): "je vais bien" is only small talk, as "let me know" is.
# "Vérifions game.py" too, but only at the start of a sentence: "ici, nous vérifions que..." explains the code
ANNOUNCE: re.Pattern = re.compile(
    r"\b(?:je vais (?:[\w']+ ){0,2}?[\w']+(?:er|ir|re|oir)|je m'apprête à|laisse-moi"
    r"|i will|i'll|let me(?! know)|let's|i am going to|i'm going to)\b"
    r"|(?:^|(?<=[.!?:] ))(?:vérifi|regard|lis|ajout|corrige|modifi|examin|cherch|cré|consult|voy|commenç"
    r"|analys|ouvr|test|remplaç|renomm)ons\b",
    re.IGNORECASE | re.MULTILINE
)

# Logged whole elsewhere (the reply and its stats by the model, the tool calls by __call): not once more per event
UNLOGGED: frozenset[str] = frozenset({
    CHAT_TEXT, CHAT_THINKING, CHAT_REPLY, MODEL_CALL, TOOL_CALL_STARTED, TOOL_CALL_ENDED
})

# Where the context Louis adds starts, after the system prompt
CONTEXT: str = "\n\n# Contexte\n"

CANCELLED_TOOL: str = "Annulé : l'utilisateur a interrompu Louis avant la fin de cet outil."

# The same call (tool and arguments) made this many times already for a message is refused: the model goes round in
# circles. After MAX_REFUSED refused calls, the turn stops
SAME_CALLS : int = 2
MAX_REFUSED: int = 3
REPEATED_CALL: str = (
    "Erreur : tu as déjà fait exactement cet appel 2 fois pour cette demande. N'en refais pas un troisième : "
    "utilise ce que tu sais déjà, lis une autre partie, ou réponds à l'utilisateur. S'il n'a pas marché, dis-lui "
    "ce qui a échoué : ne dis jamais avoir fait ce qui n'a pas été fait."
)
# The model sometimes asks for dozens of calls at once, often the same ones again (a list gone wrong): the first
# MAX_CALLS different ones are kept, the others never made. And the results of a round, never cut by the window, must
# still have this share of the context for one more call to run
MAX_CALLS: int   = 6
MIN_ROOM : float = 0.05
IGNORED_CALLS: str = (
    "\n[{} autres appels de ta réponse ont été ignorés (en double, ou trop nombreux à la fois) : "
    "refais ceux qui manquent dans ta prochaine réponse.]"
)
NO_ROOM: str = (
    "Erreur : les résultats de ta réponse prennent déjà trop de place dans le contexte : cet appel n'a pas été fait. "
    "Refais-le dans ta prochaine réponse."
)
EMPTY_MESSAGE: str = "Louis n'a rien répondu, deux fois : le modèle a sans doute appelé un outil qui n'existe pas ici. "
# Why, when the session called tools this version of Louis does not have: the model calls them again
GONE_TOOLS: str = (
    "Cette session a utilisé des outils absents de cette version de Louis (une autre branche ?), et le modèle les "
    "appelle encore : {tools}. Lance Louis depuis une version qui les a, ou repars d'une session neuve avec /clear."
)
LOOP_MESSAGE: str = (
    "Louis tournait en rond (les mêmes appels d'outils, encore et encore) : arrêté. Reformule ou découpe la demande."
)

# What the chat model reads of the messages it sums up when they leave its context: each one cut to these characters
# (a file read is what it learns from: its facts are often far from its start), and all of them to this share of its
# context. The summaries added up are merged into a shorter one past SUMMARY_CHARS
SUMMARY_MESSAGE: int   = 2000
SUMMARY_RESULT : int   = 6000
SUMMARY_SHARE  : float = 0.4
SUMMARY_CHARS  : int   = 3000

# Calls of a tool the guard refuses in a turn before the tool is withdrawn until the next message: the model
# may redo a call without the sensitive data once, but qwen3 can also ask the same one again and again
REFUSED_CALLS: int = 2

# What the model says of its draft in the reasoning loop (reason.verify): JSON, for no text to be read into a verdict.
# Never one of the schemas of /json: the user does not ask for it. Ollama has the fields written in this order: the
# claims checked again first, the verdict last. Asked first, the verdict is given before anything is looked at, and
# the rest only backs it up (ok in 11 tokens for 17 × 23 = 381). Each claim gives where it was found: checked again
# without one, the model finds a file it never read in its own draft. A few problems, each one short: enough to fix them
MAX_CHECKS   : int = 6
MAX_PROBLEMS : int = 5
PROBLEM_CHARS: int = 300
CRITIQUE: dict = {
    "type": "object",
    "properties": {
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string", "description": "une affirmation importante de la réponse (fait, calcul, "
                                                              "chemin, valeur, action faite)"},
                    "source": {"type": "string", "description": "où tu la retrouves : le résultat d'un outil (lequel, et "
                                                               "ce qu'il dit), le calcul refait pas à pas, ou "
                                                               "\"introuvable\". La réponse vérifiée n'est jamais une source"},
                    "holds": {"type": "boolean", "description": "true seulement si la source la confirme"}
                },
                "required": ["claim", "source", "holds"],
                "additionalProperties": False
            },
            "minItems": 1,
            "maxItems": MAX_CHECKS,
            "description": "chaque affirmation importante de la réponse, vérifiée de nouveau"
        },
        "problems": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": MAX_PROBLEMS,
            "description": "les vrais problèmes trouvés par ces vérifications, une phrase chacun, [] s'il n'y en a aucun"
        },
        "ok": {"type": "boolean", "description": "true seulement si aucune vérification n'a trouvé de problème"}
    },
    "required": ["checks", "problems", "ok"],
    "additionalProperties": False
}

# A file a draft names: a path with the extension of a file of code, of data or of documentation. Never a piece of a
# URL or of a longer path, nor a number (1.2, 3.13)
CITED_FILE: re.Pattern = re.compile(
    r"(?<![\w/.:-])((?:[\w-]+/)*[\w-]+\.(?:py|pyi|js|jsx|ts|tsx|json|jsonl|md|txt|rst|ya?ml|toml|ini|cfg|co|c|h|cpp|hpp|cc"
    r"|go|rs|java|kt|rb|php|sh|bash|html|css|scss|sql|csv|xml|lock))(?![\w/-])"
)
UNSOURCED: str = (
    "{path} : aucun outil ne l'a lu, listé ni écrit dans cette session, ce que la réponse en dit n'a pas de source. "
    "Lis-le avant d'en parler, ou dis que tu ne l'as pas lu."
)

def unsourced(draft: str, history: list[dict]) -> list[str]:
    """
        The files a draft names that no tool of the session read, listed or wrote: the model can only have made up
        what it says of them. Checked by the code, not asked to the model: a 9B model finds them in its own draft. A
        path is found by its file name alone: the tools show it from the project root (/model/reply.py) or under its
        folder (tree), the model from anywhere (src/model/reply.py). A made-up file with the name of a real one goes
        through: better than asking again for an answer that was right. What the user wrote is no source: they ask,
        the tools tell
    """
    sources: str = "\n".join(
        (message.get("content") or "") if message["role"] == "tool" else
        json.dumps([call.get("function", {}).get("arguments") for call in message.get("tool_calls") or []],
                   ensure_ascii=False)
        for message in history if message["role"] in ("tool", "assistant")
    )
    found: list[str] = []
    for path in dict.fromkeys(match.group(1) for match in CITED_FILE.finditer(draft)):
        if not re.search(rf"(?<![\w.-]){re.escape(path.split('/')[-1])}(?![\w-])", sources):
            found.append(path)
    return found

class App:
    """ App Class: runs the conversation, and tells everything through the bus, never printing itself """
    def __init__(self, settings: dict[str], system_prompt: str, user: User, stream: Interface,
                 monitor: Recorder | None = None):
        """
            Init the Application class, on a new session of the user, shown by the interface stream.
            With a monitor, every call to the model and to the tools is recorded, for the metrics
        """
        self.__settings: dict[str] = settings
        self.__user: User = user
        self.__system_prompt: str = system_prompt
        self.__think: bool = bool(settings.get("chat.think", False))
        self.__react: bool = bool(settings.get("reason.enabled", False))

        self.__bus: EventBus = EventBus()
        # Subscribed first: an event is logged before any other handler reacts to it
        self.__bus.subscribe(lambda event: event.name in UNLOGGED or log_event(event))
        # Before APP_STARTED: the run is recorded with its model
        if monitor is not None:
            monitor.bind(self.__bus)
        # The interface asks the user (TOOL_BEGFOR_PERMISSION) and answers (TOOL_GRANT_PERMISSION)
        self.__permissions: PermissionManager = PermissionManager(self.__bus)

        self.__toolManager: ToolManager = ToolManager()\
            .register(TreeTool())\
            .register(CatTool())\
            .register(EditTool())\
            .register(WriteTool())\
            .register(SearchTool())\
            .register(MkdirTool())\
            .register(InternetTool())\
            .register(GitTool())\
            .register(PullRequestTool())\

        # Code runs in a container: no docker, or the setting off, and the model is not offered the tool
        if settings.get("sandbox.enabled", True) and sandbox_available():
            self.__toolManager.register(RunTool())

        log.info(f"[app] tools: {', '.join(tool['function']['name'] for tool in self.__toolManager.all())}")

        # What the model sees of the session: cut down before it overflows the context, instead of Ollama cutting it
        # With chat.compact.summary, what it leaves out is summed up by the model, which reads the summary instead
        self.__window: ContextWindow = ContextWindow(
            settings.get("chat.context", 12288), self.__toolManager.all(),
            self.__summarize if settings.get("chat.compact.summary", True) else None
        )

        # What the user indexed, looked up by the model with search_knowledge. Nothing is read or created on the disk
        # before something is indexed, and the tool is only offered while there is something to look up
        self.__knowledge: Knowledge | None = Knowledge.from_settings(settings, self.__bus) if settings.get("rag.enabled", False) else None
        self.__knowledge_tool: KnowledgeTool = KnowledgeTool()
        self.offer_knowledge()
        # The files read in another session are not in the history of this one: they must be read again to be edited
        self.__seen_files: SeenFiles = SeenFiles()
        self.__bus.subscribe(self.__on_session_changed, SESSION_CREATED, SESSION_RESUMED)

        self.__commands: CommandTree = CommandTree()\
            .register(ClearCommand())\
            .register(SessionsCommand())\
            .register(ResumeCommand())\
            .register(JsonCommand())\
            .register(SchemasCommand())\
            .register(ExportCommand())\
            .register(ShareCommand())\
            .register(SharesCommand())\
            .register(UnshareCommand())\
            .register(ToggleThinkCommand())\
            .register(IndexCommand())\
            .register(UnindexCommand())\
            .register(FindCommand())\

        # NOTE: Raisable
        self.__model : OllamaModel = OllamaModel(settings["chat.uri"], f"{settings["chat.model.name"]}:{settings["chat.model.parameters"]}")

        # NOTE: Raisable. Loaded after the model: a model that does not answer fails before NeMo takes its time to load
        self.__guard: Guard | None = Guard(self.__bus) if settings.get("guard.enabled", False) else None
        # The calls the guard refused in the current turn, by tool: counted again from 0 on each message
        self.__refused: Counter[str] = Counter()

        self.__stream: Interface = stream
        # The interface shows what happens (the conversation, the commands...) by listening to the bus
        self.__stream.bind(self.__bus)
        # The titles and summaries of the sessions, the welcome of a new one: a small model, in its own thread. Started
        # before the first session, which it welcomes; never for a script that asks one question and quits
        if settings.get("scribe.model") and stream.describes and (user.db is not None or stream.welcomes):
            Scribe(settings, self.__bus, user.db.path if user.db is not None else None, user.id, welcome=stream.welcomes)
        self.__bus.dispatch(
            APP_STARTED,
            model=self.__model.model,
            think=self.think,
            commands=[command.describe() for command in self.__commands.commands]
        )

        # Started once the model answers: a failed start leaves no empty session behind
        self.new_session()

    @property
    def stream(self) -> Interface:
        """ Get the current stream (interface) """
        return self.__stream

    @property
    def events(self) -> EventBus:
        """ Get the event bus: dispatch there what the user must know, the interfaces show it """
        return self.__bus

    @property
    def user(self) -> User:
        """ Get the user talking to Louis """
        return self.__user

    @property
    def session(self) -> Session:
        """ Get the current session of the user, where the conversation is kept """
        return self.__user.current_session

    @property
    def model(self) -> OllamaModel:
        """ Returns the current model """
        return self.__model

    @property
    def think(self) -> bool:
        """ Returns if thinking is activate """
        return self.__think and self.model.thinking

    @think.setter
    def think(self, state: bool) -> None:
        """ Set the current thinking mode, for the next requests """
        if self.model.thinking:
            self.__think = state

    @property
    def react(self) -> bool:
        """ Whether the messages are answered by the reasoning loop (ReAct, /react) """
        return self.__react

    @react.setter
    def react(self, state: bool) -> None:
        """ Answer the next messages by the reasoning loop, or as usual """
        self.__react = state

    def new_session(self, system_prompt: str | None = None) -> Session:
        """ Start a new session of the user, on the given system prompt or on the one Louis started with """
        session: Session = self.__user.new_session(os.getcwd())
        session.add("system", (system_prompt or self.__system_prompt).rstrip() + self.__context())
        self.__bus.dispatch(
            SESSION_CREATED,
            user=self.__user.name,
            persistent=not self.__user.is_anonymous,
            custom_prompt=bool(system_prompt)
        )
        self.__estimate_context()
        return session

    def __context(self) -> str:
        """
            What the model can not guess, put after its prompt: the user, and the date (for web_search). Never the
            folder of the project: the model gives its name to the tools as a path, which they do not find
        """
        lines: list[str] = [f"- Date : {date.today().isoformat()}"]
        if not self.__user.is_anonymous:
            lines.insert(0, f"- Utilisateur : {self.__user.name}")
        return CONTEXT + "\n".join(lines) + "\n"

    def __prompt(self) -> str:
        """ The system prompt of the current session, without the context put after it: the date changes it every day """
        messages = self.session.messages
        if not messages or messages[0].role != "system":
            return ""
        prompt, found, _ = messages[0].content.rpartition(CONTEXT)
        return prompt if found else messages[0].content

    def __on_session_changed(self, event: Event) -> None:
        """ Another session: nothing of it is cut or read yet. A resumed one fills the context with its history """
        self.__window.reset()
        self.__seen_files.clear()
        if event.name == SESSION_RESUMED:
            self.__estimate_context()

    def __history(self) -> list[dict]:
        """
            The session as it is sent, without the empty replies saved before they were kept out: read again, they
            lead the model to more of them
        """
        return [message for message in self.session.history
                if message["role"] != "assistant" or message["content"].strip() or message.get("tool_calls")]

    def __estimate_context(self) -> None:
        """ Tell how full the context is with the current session, as it will be sent, before the model measures it """
        # An estimate: what it leaves out is summed up by the next request, never here (a /resume does not wait for it)
        messages, _ = self.__window.view(self.__history(), summarize=False)
        self.__bus.dispatch(CHAT_CONTEXT, used=self.__window.tokens(messages), size=self.__window.size, estimated=True)

    def __view(self) -> list[dict]:
        """ The session as the model sees it: its old tool results cut down, and told, once the context fills up """
        messages, cut = self.__window.view(self.__history())
        if cut:
            used: int = self.__window.tokens(messages)
            log.info(f"[app] context cut down: {cut['results']} tool results, {cut['dropped']} messages left out"
                     f"{' and summed up' if cut['summarized'] else ''}, {used} tokens left of {self.__window.size}")
            self.__bus.dispatch(CHAT_COMPACTED, **cut, used=used, size=self.__window.size)
            self.__bus.dispatch(CHAT_CONTEXT, used=used, size=self.__window.size, estimated=True)
        return messages

    def __summarize(self, previous: str, left: list[dict]) -> str | None:
        """
            The messages left out of the context, summed up by the chat model for itself, after what it summed up before:
            it reads them after its system prompt, merged into a shorter summary once they grow past SUMMARY_CHARS.
            None if the model fails: they are then only left out
        """
        parts: list[str] = []
        for message in left:
            content: str = message.get("content") or ""
            most: int = SUMMARY_RESULT if message["role"] == "tool" else SUMMARY_MESSAGE
            text: str = content if len(content) <= most else content[:most] + " […]"
            who: str = {"user": "Utilisateur", "assistant": "Toi"}.get(message["role"], f"Résultat de {message.get('tool_name') or 'un outil'}")
            calls: str = ", ".join(
                f"{call['function']['name']} {json.dumps(call['function'].get('arguments') or {}, ensure_ascii=False)[:200]}"
                for call in message.get("tool_calls") or []
            )
            parts.append(f"{who} : {text}" + (f"\n  (appels : {calls})" if calls else ""))
        text: str = "\n".join(parts)
        room: int = int(self.__window.size * SUMMARY_SHARE * CHARS_PER_TOKEN)
        if len(text) > room:
            text = "[…]\n" + text[-room:]
        try:
            block: str = self.__chat([{"role": "system", "content": SUMMARY_PROMPT},
                                      {"role": "user", "content": text}], [], None, think=False).content.strip()
            summary: str = f"{previous}\n{block}".strip()
            if len(summary) > SUMMARY_CHARS:
                summary = self.__chat([{"role": "system", "content": MERGE_PROMPT},
                                       {"role": "user", "content": summary}], [], None, think=False).content.strip()
        except ModelException as e:
            log.warning(f"[app] {len(left)} messages left out of the context without a summary: {e.message}")
            return None
        log.info(f"[app] {len(left)} messages left out of the context, summed up:\n{summary}")
        return summary[:SUMMARY_CHARS * 2] or None

    @property
    def settings(self) -> dict[str]:
        """ Get the settings Louis runs with, for the tools to read theirs """
        return self.__settings

    @property
    def permissions(self) -> PermissionManager:
        """ Get the permission manager, for the tools to ask before acting """
        return self.__permissions

    @property
    def seen_files(self) -> SeenFiles:
        """ Get the files the model has read or written in this session, for edit_file to check """
        return self.__seen_files

    @property
    def knowledge(self) -> Knowledge | None:
        """ Get the knowledge base the user indexed, None if it is turned off (rag.enabled) """
        return self.__knowledge

    def offer_knowledge(self) -> None:
        """
            Offer search_knowledge to the model while something is indexed, and withdraw it when nothing is any more.
            Its description lists what the base holds, made again here after each change: the model looks up only
            what it knows is there
        """
        if self.__knowledge is None:
            return
        name: str = self.__knowledge_tool.name
        if self.__knowledge.empty:
            if self.__toolManager.has(name):
                self.__toolManager.unregister(name)
                log.info(f"[app] {name} withdrawn")
        else:
            self.__knowledge_tool.refresh(self.__knowledge.catalog())
            if not self.__toolManager.has(name):
                self.__toolManager.register(self.__knowledge_tool)
                log.info(f"[app] {name} offered")
        # The description may have grown or shrunk: the room the tools take in the context with it
        self.__window.set_tools(self.__toolManager.all())

    def run(self) -> int:
        """ Run the application: answer the messages of the user, until the input ends or Ctrl+C there """
        while True:
            try:
                u = self.stream.getUserInput()
            except (KeyboardInterrupt, EOFError) as e:
                log.info(f"[app] closed by the user ({type(e).__name__})")
                self.__bus.dispatch(APP_STOPPED, reason="interrupt" if isinstance(e, KeyboardInterrupt) else "eof")
                return 0
            if not u.strip():
                continue
            log.info(f"[user] {u.strip()}")
            try:
                if not self.__commands.fetch(u, self):
                    self.reason(u) if self.__react else self.__answer(u)
            except KeyboardInterrupt:
                # Ctrl+C in a command: back to the input, the answers handle it themselves
                log.info("[app] command interrupted by the user")

    def structured(self, text: str, name: str, schema: dict) -> tuple[bool, Any]:
        """
            Answer a message of the user with JSON that matches the schema (its name for the user), without tools:
            Ollama constrains the reply, then it is checked (a reply cut, or a constraint the grammar can not hold),
            and asked again with what is wrong, structured.attempts times at most. Whether it matches, and its JSON.
            Kept in the session as JSON when it matches. With the guard, the reply is checked again once masked: a
            reply that no longer matches is refused, asking again would only mask it again
        """
        self.__bus.dispatch(CHAT_TURN_STARTED)
        most: int = max(1, int(self.__settings.get("structured.attempts", 3)))
        attempts: int = 0
        errors: list[str] = []
        data: Any = None
        try:
            question: str = text
            if self.__guard is not None:
                verdict: Verdict = self.__guard.check_input(text)
                if verdict.refused:
                    self.__bus.dispatch(CHAT_TURN_ENDED, reason="refused", message=verdict.content)
                    return False, None
                question = verdict.content

            saved: bool = self.session.saved
            self.session.add("user", question)
            if not saved and self.session.saved:
                self.__bus.dispatch(SESSION_SAVED, id=self.session.id)
            # The schema is told for this request only: the session keeps the question as the user asked it
            messages: list[dict] = self.__view()
            messages[-1] = {**messages[-1], "content": question + instruction(schema)}

            while attempts < most:
                attempts += 1
                reply: Reply = self.__chat(messages, [], None, schema=schema)
                if reply.cut:
                    data, errors = None, [f"réponse coupée : elle a dépassé {self.__settings.get('chat.predict')} tokens"]
                else:
                    data, errors = checked(reply.content, schema)
                if not errors and self.__guard is not None:
                    verdict = self.__guard.check_output(question, reply.content)
                    if verdict.refused:
                        self.__bus.dispatch(CHAT_TURN_ENDED, reason="refused", message=verdict.content)
                        return False, None
                    if verdict.content != reply.content:
                        data, errors = checked(verdict.content, schema)
                        if errors:
                            errors = ["le garde-fou a masqué des données sensibles, et la réponse masquée ne respecte "
                                      "plus le schéma"] + errors
                            break
                if not errors:
                    break
                log.info(f"[app] structured reply #{attempts} does not match {name}: {'; '.join(errors)}")
                messages = messages + [{"role": "assistant", "content": reply.content},
                                       {"role": "user", "content": retry(errors)}]

            valid: bool = not errors
            if valid:
                self.session.add("assistant", shown(data))
            self.__bus.dispatch(
                STRUCTURED_REPLY, schema=name, valid=valid, data=data if valid else None, attempts=attempts,
                errors=errors
            )
            self.__bus.dispatch(CHAT_TURN_ENDED, reason="done" if valid else "invalid", message=None if valid else (
                f"Réponse invalide pour le schéma {name} après {attempts} essai{'s' if attempts > 1 else ''} : "
                + "; ".join(errors)
            ))
            return valid, data if valid else None
        except KeyboardInterrupt:
            log.info("[app] structured reply cancelled by the user")
            self.__bus.dispatch(CHAT_TURN_ENDED, reason="cancelled", message=None)
        except ModelException as e:
            log.error(f"[app] the model failed: {e.message}")
            self.__bus.dispatch(CHAT_TURN_ENDED, reason="error", message=e.message)
        except Exception as e:
            log.exception("[app] the structured reply failed")
            self.__bus.dispatch(CHAT_TURN_ENDED, reason="error", message=f"Erreur interne : {type(e).__name__}: {e}")
        return False, None

    def __answer(self, text: str) -> None:
        """
            Answer a message of the user: the model replies, calling tools, until a reply calls none.
            With the guard, the model only reads what the input rails let through, and the user only
            reads what the output rails let through. Whatever goes wrong in the guard ends the turn:
            a guard that cannot check never lets a message go unchecked
        """
        self.__bus.dispatch(CHAT_TURN_STARTED)
        rounds: int = self.__settings.get("chat.tools.maxdepth", 8)
        nudged: bool = False
        emptied: bool = False
        # A reply can only be checked whole: with the guard, it is shown once checked, not as it is written
        stream: Callable | None = None if self.__guard else lambda chunk: self.__bus.dispatch(CHAT_TEXT, text=chunk)
        self.__refused.clear()
        # The calls made for this message, and those refused for being the same again: the model goes round in circles
        made: Counter = Counter()
        repeats: int = 0
        try:
            question: str = text
            if self.__guard is not None:
                verdict: Verdict = self.__guard.check_input(text)
                # Refused: kept out of the session, the model would read it again on the next message
                if verdict.refused:
                    self.__bus.dispatch(CHAT_TURN_ENDED, reason="refused", message=verdict.content)
                    return
                question = verdict.content

            saved: bool = self.session.saved
            self.session.add("user", question)
            if not saved and self.session.saved:
                self.__bus.dispatch(SESSION_SAVED, id=self.session.id)

            for _ in range(rounds):
                reply: Reply = self.__chat(
                    self.__view(),
                    [tool for tool in self.__toolManager.all() if self.__refused[tool["function"]["name"]] < REFUSED_CALLS],
                    stream
                )
                ignored: int = self.__keep_calls(reply)
                if self.__guard is not None and reply.content:
                    self.__screen(question, reply)
                # Nothing to read and no call: the model called a tool it is not offered, or wrote nothing. Never
                # saved, and asked again once with the tools it has: the user is never left without an answer
                if not reply.content.strip() and not reply.tool_calls:
                    if self.__empty(emptied):
                        return
                    emptied = True
                    continue
                self.session.add("assistant", reply.content, tool_calls=reply.tool_calls)
                # What Ollama counted of the prompt: the window measures its estimate on it, to cut in time
                self.__window.measured(reply.prompt_tokens)
                # Without the counts of Ollama (a reply cut short), the last known value stays
                if reply.tokens:
                    self.__bus.dispatch(
                        CHAT_CONTEXT, used=reply.tokens, size=self.__settings.get("chat.context", 12288), estimated=False
                    )
                self.__bus.dispatch(CHAT_REPLY, content=reply.content, tools=[call.name for call in reply.tool_calls])
                if reply.cut and not reply.tool_calls:
                    self.__end_cut()
                    return

                if not reply.tool_calls:
                    # Once per message, so a wrong guess costs one round and never loops
                    if nudged or not ANNOUNCE.search(reply.content):
                        self.__bus.dispatch(CHAT_TURN_ENDED, reason="done", message=None)
                        return
                    nudged = True
                    log.info("[app] the model announced an action without calling a tool: nudging it")
                    self.__bus.dispatch(CHAT_NUDGED)
                    self.session.add("user", NUDGE_PROMPT)
                    continue

                repeats += self.__run_calls(reply.tool_calls, ignored, made)
                if repeats >= MAX_REFUSED:
                    log.warning(f"[app] {repeats} calls refused for being the same again: the model goes round in circles")
                    self.__bus.dispatch(CHAT_TURN_ENDED, reason="loop", message=LOOP_MESSAGE)
                    return
        except KeyboardInterrupt:
            log.info("[app] turn cancelled by the user")
            self.__bus.dispatch(CHAT_TURN_ENDED, reason="cancelled", message=None)
            return
        except ModelException as e:
            log.error(f"[app] the model failed: {e.message}")
            self.__bus.dispatch(CHAT_TURN_ENDED, reason="error", message=e.message)
            return
        except Exception as e:
            log.exception("[app] the turn failed")
            self.__bus.dispatch(CHAT_TURN_ENDED, reason="error", message=f"Erreur interne : {type(e).__name__}: {e}")
            return

        log.warning(f"[app] stopped after {rounds} rounds of tool calls")
        self.__bus.dispatch(CHAT_TURN_ENDED, reason="rounds", message=f"Arrêté après {rounds} tours d'appels d'outils.")

    def reason(self, text: str) -> None:
        """
            Answer a message of the user by the reasoning loop (ReAct): at each step, the model says what it knows and
            what it will do, then calls tools, and reads their results before the next one (REASONING_STEP). A reply
            that calls none is a draft: with reason.verify, the model checks it first (REASONING_CHECK), and writes it
            again with its problems, reason.attempts times at most. The last one is checked too, and given whatever
            its check says: the user reads what is wrong with it. A draft is only shown once checked, never as it is
            written: a rejected one is never read by the user. The session keeps every step, the rejected drafts and
            what was wrong with them: the trace of how the answer was reached. The guard checks every reply as
            __answer does, and masks the thoughts it shows
        """
        self.__bus.dispatch(CHAT_TURN_STARTED)
        rounds: int = self.__settings.get("chat.tools.maxdepth", 8)
        verify: bool = bool(self.__settings.get("reason.verify", True))
        most: int = max(0, int(self.__settings.get("reason.attempts", 2)))
        checks: int = 0
        emptied: bool = False
        self.__refused.clear()
        made: Counter = Counter()
        repeats: int = 0
        try:
            question: str = text
            if self.__guard is not None:
                verdict: Verdict = self.__guard.check_input(text)
                if verdict.refused:
                    self.__bus.dispatch(CHAT_TURN_ENDED, reason="refused", message=verdict.content)
                    return
                question = verdict.content

            saved: bool = self.session.saved
            self.session.add("user", question)
            if not saved and self.session.saved:
                self.__bus.dispatch(SESSION_SAVED, id=self.session.id)

            for step in range(1, rounds + 1):
                reply: Reply = self.__chat(
                    self.__reasoning_view(question),
                    [tool for tool in self.__toolManager.all() if self.__refused[tool["function"]["name"]] < REFUSED_CALLS],
                    None
                )
                ignored: int = self.__keep_calls(reply)
                refused: bool = self.__guard is not None and bool(reply.content) and self.__screen(question, reply, show=False)
                if not reply.content.strip() and not reply.tool_calls:
                    if self.__empty(emptied):
                        return
                    emptied = True
                    continue
                self.__window.measured(reply.prompt_tokens)
                if reply.tokens:
                    self.__bus.dispatch(
                        CHAT_CONTEXT, used=reply.tokens, size=self.__settings.get("chat.context", 12288), estimated=False
                    )
                # The thought: what the model wrote beside its calls, else what it thought (think). A draft is no thought
                thought: str = (reply.content if reply.tool_calls else "").strip() or reply.thinking.strip()
                if self.__guard is not None:
                    thought = self.__guard.hide({"thought": thought})["thought"]
                self.__bus.dispatch(REASONING_STEP, step=step, thought=thought, tools=[call.name for call in reply.tool_calls])

                if reply.tool_calls:
                    self.session.add("assistant", reply.content, tool_calls=reply.tool_calls)
                    repeats += self.__run_calls(reply.tool_calls, ignored, made)
                    if repeats >= MAX_REFUSED:
                        log.warning(f"[app] {repeats} calls refused for being the same again: the model goes round in circles")
                        self.__bus.dispatch(CHAT_TURN_ENDED, reason="loop", message=LOOP_MESSAGE)
                        return
                    continue

                if reply.cut:
                    self.session.add("assistant", reply.content)
                    self.__end_cut()
                    return
                # A draft. A refusal of the guard is no answer of the model to check: it goes as it is
                ok, problems = True, []
                if verify and not refused:
                    checks += 1
                    ok, problems = self.__verify(reply.content)
                    self.__bus.dispatch(REASONING_CHECK, attempt=checks, ok=ok, problems=problems)
                self.session.add("assistant", reply.content)
                if not ok and checks <= most:
                    log.info(f"[app] draft #{checks} rejected: written again")
                    self.session.add("user", REVISE_PROMPT.format(problems="\n".join(f"- {problem}" for problem in problems)))
                    continue
                self.__bus.dispatch(CHAT_TEXT, text=reply.content)
                self.__bus.dispatch(CHAT_REPLY, content=reply.content, tools=[])
                self.__bus.dispatch(CHAT_TURN_ENDED, reason="done", message=None)
                return
        except KeyboardInterrupt:
            log.info("[app] reasoning cancelled by the user")
            self.__bus.dispatch(CHAT_TURN_ENDED, reason="cancelled", message=None)
            return
        except ModelException as e:
            log.error(f"[app] the model failed: {e.message}")
            self.__bus.dispatch(CHAT_TURN_ENDED, reason="error", message=e.message)
            return
        except Exception as e:
            log.exception("[app] the reasoning failed")
            self.__bus.dispatch(CHAT_TURN_ENDED, reason="error", message=f"Erreur interne : {type(e).__name__}: {e}")
            return

        log.warning(f"[app] reasoning stopped after {rounds} steps")
        self.__bus.dispatch(CHAT_TURN_ENDED, reason="rounds", message=f"Arrêté après {rounds} étapes de raisonnement.")

    def __reasoning_view(self, question: str) -> list[dict]:
        """
            The session as the model sees it, with the request being answered told how to reason (REACT_PROMPT): for
            this request only, the session keeps it as the user asked it
        """
        messages: list[dict] = self.__view()
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user" and messages[i]["content"] == question:
                messages[i] = {**messages[i], "content": question + REACT_PROMPT}
                break
        return messages

    def __empty(self, emptied: bool) -> bool:
        """
            A reply with nothing to read and no call: the model called a tool it is not offered, or wrote nothing. Never
            saved, and asked again once with the tools it has: the user is never left without an answer. Whether the
            turn ends (empty again)
        """
        if emptied:
            log.warning("[app] empty reply again: the turn ends")
            gone: list[str] = sorted({call["function"]["name"] for message in self.session.history
                                      for call in message.get("tool_calls") or []
                                      if not self.__toolManager.has(call["function"]["name"])})
            why: str = GONE_TOOLS.format(tools=", ".join(gone)) if gone else "Reformule ta demande."
            self.__bus.dispatch(CHAT_TURN_ENDED, reason="empty", message=EMPTY_MESSAGE + why)
            return True
        log.warning("[app] empty reply (a call to a tool it is not offered?): asking again")
        names: str = ", ".join(schema["function"]["name"] for schema in self.__toolManager.all())
        self.session.add("user", EMPTY_PROMPT.format(tools=names))
        return False

    def __end_cut(self) -> None:
        """ The reply reached the most tokens it may take, calling no tool: the turn ends, it was going round in circles """
        log.warning("[app] the reply reached the most tokens it may take: cut")
        self.__bus.dispatch(CHAT_TURN_ENDED, reason="length", message=(
            f"Réponse coupée : le modèle a dépassé {self.__settings.get('chat.predict')} tokens sans finir "
            "(il tournait peut-être en rond). Demande une partie plus petite."
        ))

    @staticmethod
    def __keep_calls(reply: Reply) -> int:
        """ Keep the first MAX_CALLS different calls of the reply: how many of them are left out (the same again, or too many) """
        calls: list[ToolCall] = []
        for call in reply.tool_calls:
            if call not in calls and len(calls) < MAX_CALLS:
                calls.append(call)
        ignored: int = len(reply.tool_calls) - len(calls)
        if ignored:
            log.warning(f"[app] {len(reply.tool_calls)} calls in one reply: {ignored} ignored")
        reply.tool_calls = calls
        return ignored

    def __run_calls(self, calls: list[ToolCall], ignored: int, made: Counter) -> int:
        """
            Run the calls of a reply, each result kept in the session, the last one telling the ignored calls. A call
            made SAME_CALLS times already for this message (counted in made) is refused, as one whose results would
            no longer fit in the context. How many were refused for being the same again: the model goes round in
            circles. Cancelled, each call not answered yet still gets an answer
        """
        pending: list[ToolCall] = list(calls)
        repeats: int = 0
        # The share of the context the results of this round may still take
        room: float = ROUND
        try:
            while pending:
                call: ToolCall = pending[0]
                key: str = f"{call.name} {json.dumps(call.arguments, sort_keys=True, ensure_ascii=False, default=str)}"
                reason: str | None = None
                if made[key] >= SAME_CALLS:
                    reason = REPEATED_CALL
                    repeats += 1
                elif room < MIN_ROOM:
                    reason = NO_ROOM
                else:
                    made[key] += 1
                result: str = self.__call(call, refused=reason, most=min(MAX_RESULT, room))
                room -= share(result, self.__window.size, self.__window.ratio)
                if ignored and len(pending) == 1:
                    result += IGNORED_CALLS.format(ignored)
                self.session.add("tool", result, tool_name=call.name)
                pending.pop(0)
        except KeyboardInterrupt:
            for call in pending:
                self.session.add("tool", CANCELLED_TOOL, tool_name=call.name)
            raise
        return repeats

    def __verify(self, draft: str) -> tuple[bool, list[str]]:
        """
            The model checks the draft of its answer against what it read in this session (the draft is not in it yet),
            as JSON that matches CRITIQUE, without tools nor thinking: whether it may go, and its problems. A check the
            model can not give (it fails, its reply is cut or does not match) counts as ok: it never holds the answer
            back, the draft was the answer anyway. A draft that names files no tool read is not ok, without asking the
            model: it is written again anyway, the next check sees the rest
        """
        if missing := unsourced(draft, self.__history()):
            problems: list[str] = [UNSOURCED.format(path=path) for path in missing][:MAX_PROBLEMS]
            log.info(f"[app] draft checked: files never read: {', '.join(missing)}")
            return False, problems
        messages: list[dict] = self.__view() + [
            {"role": "assistant", "content": draft},
            {"role": "user", "content": VERIFY_PROMPT + instruction(CRITIQUE)}
        ]
        try:
            reply: Reply = self.__chat(messages, [], None, schema=CRITIQUE, think=False)
        except ModelException as e:
            log.warning(f"[app] the draft could not be checked, it goes as it is: {e.message}")
            return True, []
        data, errors = (None, ["cut"]) if reply.cut else checked(reply.content, CRITIQUE)
        if errors:
            log.warning(f"[app] the check of the draft is no verdict, it goes as it is: {'; '.join(errors)}")
            return True, []
        checks: list[dict] = data.get("checks") or []
        problems: list[str] = [problem.strip() for problem in data["problems"] if problem.strip()]
        # A claim its source does not confirm is a problem, even when the model forgets to say so
        failed: list[dict] = [check for check in checks if not check["holds"]]
        if failed and not problems:
            problems = [f"{check['claim']} : {check['source']}" for check in failed]
        problems = [problem[:PROBLEM_CHARS] for problem in problems][:MAX_PROBLEMS]
        # Not ok without saying why: nothing to fix, asking again would give the same answer
        ok: bool = (data["ok"] and not failed) or not problems
        log.info(f"[app] draft checked: {'ok' if ok else 'problems: ' + '; '.join(problems)}, after:\n" + "\n".join(
            f"- {check['claim']} ({check['source']}): {'holds' if check['holds'] else 'does not hold'}" for check in checks
        ))
        return ok, [] if ok else problems

    def __chat(self, messages: list[dict], tools: list[dict], stream: Callable | None,
               schema: dict | None = None, think: bool | None = None) -> Reply:
        """
            Ask the model for its next reply, and tell how the request went (MODEL_CALL), even when it fails or the
            user cancels it: the monitoring records every call, with its latency and its tokens.
            With a schema, the reply is JSON that matches it, and the model does not think first: what it would
            think is no JSON
        """
        start: float = time.perf_counter()
        reply: Reply | None = None
        status, error = "ok", None
        think = (self.think and schema is None) if think is None else think
        try:
            reply = self.__model.chat(
                messages, tools, think=think, on_text=stream,
                on_thinking=lambda chunk: self.__bus.dispatch(CHAT_THINKING, text=chunk), schema=schema
            )
            return reply
        except ModelException as e:
            status, error = "error", e.message
            raise
        except KeyboardInterrupt:
            status = "cancelled"
            raise
        except Exception as e:
            status, error = "error", f"{type(e).__name__}: {e}"
            raise
        finally:
            self.__bus.dispatch(
                MODEL_CALL,
                model=self.__model.model,
                system=self.__prompt(),
                messages=messages,
                tools=[tool["function"]["name"] for tool in tools],
                think=think,
                status=status,
                error=error,
                latency=round(time.perf_counter() - start, 3),
                # A copy: the app changes the reply afterwards (the calls kept, the guard's mask)
                reply=asdict(reply) if reply is not None else None
            )

    def __screen(self, question: str, reply: Reply, show: bool = True) -> bool:
        """
            Put the reply through the output rails, then show it: masked, or replaced by the refusal.
            Kept in the session as it is shown, so the model never reads again what the user could not.
            A refused reply calls no tool: what the model meant to do with it is not known. Without show, it is only
            screened (the reasoning loop shows a reply once checked). Whether it was refused
        """
        verdict: Verdict = self.__guard.check_output(question, reply.content)
        reply.content = verdict.content
        if verdict.refused:
            reply.tool_calls = []
        if show:
            self.__bus.dispatch(CHAT_TEXT, text=reply.content)
        return verdict.refused

    def __screen_call(self, call: ToolCall, producer: str) -> str | None:
        """
            Put a call of the model through the tool rails before it runs: the refusal to give back as its
            result, or None to run it. The calls of the user and of Louis are not the model's: they go through.
            A guard that cannot check refuses: an unchecked call never runs
        """
        if self.__guard is None or producer != "model":
            return None
        try:
            verdict: Verdict = self.__guard.check_tool_call(call)
        except Exception as e:
            log.exception(f"[guard] the check of {call.name} failed")
            return (f"Erreur : le garde-fou n'a pas pu vérifier l'appel à '{call.name}' ({type(e).__name__}), "
                    "il n'a pas été lancé.")
        if not verdict.refused:
            return None
        self.__refused[call.name] += 1
        if self.__refused[call.name] >= REFUSED_CALLS:
            log.info(f"[guard] {call.name} refused {REFUSED_CALLS} times: withdrawn until the next message")
        return verdict.content

    def __screen_result(self, call: ToolCall, result: str) -> str:
        """
            Put what a tool read outside the project (the knowledge base: documents nobody here wrote) through the
            tool result rails before the model reads it: the passages that give it orders taken out, the sensitive data
            masked. Whoever asked for the call. A guard that cannot check gives nothing: an unchecked result is never read
        """
        if self.__guard is None or not self.__guard.screens_result(call.name):
            return result
        try:
            return self.__guard.check_tool_result(call.name, result).content
        except Exception as e:
            log.exception(f"[guard] the check of the result of {call.name} failed")
            return (f"Erreur : le garde-fou n'a pas pu vérifier le résultat de '{call.name}' ({type(e).__name__}), "
                    "il ne t'est pas donné.")

    def __call(self, call: ToolCall, producer: str = "model", *, refused: str | None = None,
               most: float = MAX_RESULT) -> str:
        """
            Run a tool, asked for by producer ("model", "user" or "system"): whatever goes wrong comes back
            as text, for the model to react. A call refused by the app is not run: refused is its result. The result
            takes at most the share most of the context
        """
        # With the guard, the interfaces show the arguments masked, as the replies are
        shown: dict = self.__guard.hide(call.arguments) if self.__guard is not None else call.arguments
        self.__bus.dispatch(TOOL_CALL_STARTED, name=call.name, arguments=shown, producer=producer)
        log.info(f"[tool] {call.name} {json.dumps(call.arguments, ensure_ascii=False)}")
        start: float = time.perf_counter()
        tool: Tool | None = self.__toolManager.get(call.name)
        if refused is not None:
            result = refused
        elif tool is None:
            names: str = ", ".join(schema["function"]["name"] for schema in self.__toolManager.all())
            result = f"Erreur : l'outil '{call.name}' n'existe pas. Les outils disponibles sont : {names}."
        elif (refusal := self.__screen_call(call, producer)) is not None:
            result = refusal
        else:
            try:
                result = tool.handle(self, **call.arguments)
                result = self.__screen_result(call, result if isinstance(result, str) else str(result))
            except Exception as e:
                log.exception(f"[tool] {call.name} failed")
                result = (f"Erreur : l'outil '{call.name}' a échoué ({type(e).__name__} : {e}). "
                          "Vérifie tes arguments, ou fais autrement.")
        result = result if isinstance(result, str) else str(result)
        # Never more than its share of the context: a whole big file would push the rest of the conversation out
        if refused is None:
            result = capped(result, self.__window.size, most, self.__window.ratio)
        # Unknown, crashed, or it could not do it (a text not found, a permission refused...): not ok
        ok: bool = not failed(result)
        duration: float = time.perf_counter() - start
        log.info(f"[tool] {call.name} done in {duration:.2f}s:\n{result}")
        self.__bus.dispatch(
            TOOL_CALL_ENDED, name=call.name, producer=producer, ok=ok, result=result, duration=round(duration, 3)
        )
        return result
