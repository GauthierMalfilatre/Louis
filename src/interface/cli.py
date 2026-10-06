##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## CLI Class that inherit from Interface
##
from interface.interface import Interface
from events.event_bus import EventBus
from events.event import Event
from events.event_list import SESSION_CREATED, SESSION_LIST, SESSION_RESUMED, COMMAND_UNKNOWN, COMMAND_ERROR
from events.event_list import TOOL_BEGFOR_PERMISSION, TOOL_GRANT_PERMISSION, THINKING_ENABLED, THINKING_DISABLED
from events.event_list import CHAT_TURN_STARTED, CHAT_TURN_ENDED, CHAT_TEXT, CHAT_REPLY, CHAT_COMPACTED
from events.event_list import TOOL_CALL_STARTED, TOOL_CALL_ENDED, APP_STOPPED, GUARD_TRIGGERED
from events.event_list import STRUCTURED_REPLY, SCHEMA_LIST
import json
import os
import re
import sys

PREVIEW_LENGTH = 70
ARGUMENT_LENGTH = 40

# The bullet of a tool call, by who wanted it: the model, the user (a command), or Louis itself
BULLETS: dict[str, str] = {"model": "●", "user": "▸", "system": "○"}

# What each tool does, said to the user: the others keep their name
LABELS: dict[str, str] = {
    "tree"      : "Arborescence",
    "cat_file"  : "Lecture",
    "search"    : "Recherche",
    "edit_file" : "Modification",
    "write_file": "Écriture",
    "mkdir"     : "Nouveau dossier",
    "web_search": "Recherche web",
}

def shorten(text: str, length: int = ARGUMENT_LENGTH) -> str:
    """ A text on one line, cut if it is too long """
    text = " ".join(str(text).split())
    return text if len(text) <= length else text[:length - 1] + "…"

def call_detail(name: str, values: dict) -> str:
    """ What a tool call is about, in a few words: its file, what it searches... """
    path = values.get("path")
    if name == "search":
        where: str = f" dans {path}" if path and path not in (".", "/") else ""
        glob: str = f" ({values['glob']})" if values.get("glob") else ""
        return f"« {shorten(values.get('pattern', ''))} »{where}{glob}"
    if name == "web_search":
        return f"« {shorten(values.get('query', ''))} »"
    if path:
        start = values.get("start_line")
        return shorten(path) + (f", dès la ligne {start}" if str(start).isdigit() and int(start) > 1 else "")
    return arguments(values)

def result_summary(name: str, result: str, ok: bool) -> str:
    """ What a tool call gave, in a few words """
    lines: list[str] = result.strip().splitlines() or [""]
    if not ok:
        return "refusé" if lines[0].startswith("Refusé") else shorten(lines[0].removeprefix("Erreur : "), PREVIEW_LENGTH)
    if name == "cat_file" and (read := re.search(r"\(lignes (\d+)-(\d+) sur \d+\)", lines[0])):
        count: int = int(read[2]) - int(read[1]) + 1
        return f"{count} ligne{'s' if count > 1 else ''} lue{'s' if count > 1 else ''}"
    if name == "tree":
        count = sum(1 for line in lines[1:] if line.strip() and not line.startswith(("…", "(")))
        return f"{count} entrée{'s' if count > 1 else ''}"
    if name == "search" and not lines[0].startswith("Aucun"):
        more = re.search(r"… (\d+) résultats de plus", result)
        count = sum(1 for line in lines if re.match(r"/\S*:\d+:", line)) + (int(more[1]) if more else 0)
        return f"{count} résultat{'s' if count > 1 else ''}"
    if name == "web_search":
        try:
            count = len(json.loads(result))
            return f"{count} résultat{'s' if count > 1 else ''}"
        except (ValueError, TypeError):
            pass
    return shorten(lines[0].removeprefix("OK : "), PREVIEW_LENGTH)

def arguments(values: dict) -> str:
    """ The arguments of a tool call on one line, each one cut if it is too long """
    parts: list[str] = []
    for key, value in values.items():
        text: str = " ".join(str(value).split())
        parts.append(f"{key}={text if len(text) <= ARGUMENT_LENGTH else text[:ARGUMENT_LENGTH - 1] + '…'}")
    return " ".join(parts)

def preview(text: str) -> str:
    """ A message on one line, cut if it is too long """
    text = " ".join(text.split())
    return text if len(text) <= PREVIEW_LENGTH else text[:PREVIEW_LENGTH - 1] + "…"

def short_path(path: str) -> str:
    """ A path, with ~ for the home folder """
    home: str = os.path.expanduser("~")
    return "~" + path[len(home):] if path == home or path.startswith(home + os.sep) else path

class CLI(Interface):
    """ Class CLI to interact with the user in the terminal """
    def __init__(self, prompt: str = "> "):
        """ Init the CLI class """
        self.__prompt: str = prompt
        # Whether the last text written ended a line: the tool calls always start their own
        self.__at_line_start: bool = True
        # "a" to a permission: the tools may act without asking, until the session changes
        self.__always: bool = False
        super().__init__()

    @property
    def promp(self) -> str:
        """ Get the prompt of the CLI """
        return self.__prompt

    def bind(self, bus: EventBus) -> "CLI":
        """ Show the conversation, the sessions and the results of the commands as text, and ask the permissions """
        # Kept to answer: a permission is granted by dispatching TOOL_GRANT_PERMISSION
        self.__bus: EventBus = bus
        bus.subscribe(lambda event: self.out("\n", end=""), CHAT_TURN_STARTED)
        bus.subscribe(self._on_text, CHAT_TEXT)
        bus.subscribe(self._on_reply, CHAT_REPLY)
        bus.subscribe(self.__on_turn_ended, CHAT_TURN_ENDED)
        bus.subscribe(self.__on_compacted, CHAT_COMPACTED)
        bus.subscribe(self._on_tool_started, TOOL_CALL_STARTED)
        bus.subscribe(self._on_tool_ended, TOOL_CALL_ENDED)
        bus.subscribe(lambda event: self.debug("\nUser has closed the session...\n"), APP_STOPPED)
        bus.subscribe(self.__on_permission, TOOL_BEGFOR_PERMISSION)
        bus.subscribe(self.__on_session_created, SESSION_CREATED)
        bus.subscribe(self.__on_session_list, SESSION_LIST)
        bus.subscribe(self.__on_session_resumed, SESSION_RESUMED)
        bus.subscribe(self._on_structured, STRUCTURED_REPLY)
        bus.subscribe(self.__on_schema_list, SCHEMA_LIST)
        bus.subscribe(self.__on_command_unknown, COMMAND_UNKNOWN)
        bus.subscribe(self.__on_command_error, COMMAND_ERROR)
        bus.subscribe(self.__on_thinking_enabled, THINKING_ENABLED)
        bus.subscribe(self.__on_thinking_disabled, THINKING_DISABLED)
        bus.subscribe(self.__on_guard, GUARD_TRIGGERED)
        return self

    def __on_turn_ended(self, event: Event) -> None:
        """ A blank line after the reply, or why it stopped """
        self._newline()
        match event.data["reason"]:
            case "done":
                self.out("")
            case "cancelled":
                self.out("(Réponse interrompue.)\n")
            case "error":
                self.out(f"Erreur : {event.data['message']}\n")
            case _:
                self.out(f"{event.data['message']}\n")

    def __on_compacted(self, event: Event) -> None:
        """   ○ Contexte allégé : the model sees less of the conversation, the user knows why it may read again """
        parts: list[str] = []
        if event.data["results"]:
            parts.append(f"{event.data['results']} anciens résultats d'outils réduits à leurs premières lignes")
        if event.data["dropped"]:
            parts.append(f"{event.data['dropped']} anciens messages mis de côté")
        self._newline()
        self.out(f"  {BULLETS['system']} Contexte allégé : {', '.join(parts)}.", dim=True)

    def _on_text(self, event: Event) -> None:
        """ A piece of the reply, as the model writes it """
        self.out(event.data["text"], end="", flush=True)

    def _on_reply(self, event: Event) -> None:
        """ The end of a reply: what comes next (a tool call, another reply) starts on its own line """
        if event.data["content"]:
            self._newline()

    def _call_parts(self, event: Event) -> tuple[str, str, str]:
        """ The bullet, the label and the detail of a tool call:  ● Lecture version.py """
        name: str = event.data["name"]
        return (BULLETS.get(event.data["producer"], BULLETS["system"]), LABELS.get(name, name),
                call_detail(name, event.data["arguments"]))

    def _result_line(self, event: Event) -> str:
        """ What the call gave, and how long it took if it was not at once:  1 ligne lue · 2.4s """
        duration: float = event.data["duration"]
        summary: str = result_summary(event.data["name"], event.data["result"], event.data["ok"])
        return summary + (f" · {duration:.1f}s" if duration >= 0.1 else "")

    def _on_tool_started(self, event: Event) -> None:
        """ The tool call, on its own line:  ● Lecture version.py """
        self._newline()
        bullet, label, detail = self._call_parts(event)
        self.out(f"  {bullet} {label} {detail}".rstrip(), flush=True)

    def _on_tool_ended(self, event: Event) -> None:
        """ What it gave, below:  ⎿ 1 ligne lue """
        self.out(f"    ⎿ {self._result_line(event)}")

    def _show_diff(self, preview: str) -> None:
        """ The diff a tool asks to apply: as it is in a plain terminal """
        self.out(preview)

    def _newline(self) -> None:
        """ Go to the next line, unless the last text written ended one """
        if not self.__at_line_start:
            self.out("")

    def __on_thinking_enabled(self, event: Event) -> None:
        """ Say the replies will be slower """
        self.out("\nRéflexion activée : Louis réfléchit avant chaque réponse, c'est plus long. /think pour la couper.\n")

    def __on_thinking_disabled(self, event: Event) -> None:
        """ Back to direct replies """
        self.out("\nRéflexion désactivée : Louis répond directement.\n")

    def __on_guard(self, event: Event) -> None:
        """ What the guard changed, dim, before the reply or the refusal:  ⛨ Message anonymisé : … """
        self._newline()
        before: bool = event.data["stage"] == "input"
        if event.data["stage"] == "tool_call":
            # Under the call, before its result:  ⎿ refusé
            self.out(f"    ⛨ Appel bloqué par le garde-fou ({', '.join(event.data['rails'])})", dim=True)
        elif event.data["action"] == "refused":
            what: str = "Message bloqué" if before else "Réponse bloquée"
            self.out(f"⛨ {what} par le garde-fou ({', '.join(event.data['rails'])})", dim=True)
        elif before:
            # The user sees what the model reads in place of the message
            self.out(f"⛨ Message anonymisé avant le modèle : {preview(event.data['content'])}", dim=True)
        else:
            self.out("⛨ Réponse anonymisée par le garde-fou", dim=True)

    def __on_permission(self, event: Event) -> None:
        """ Show what a tool wants to do and its diff, then grant it if the user agrees, or always agrees """
        preview: str = event.data.get("preview") or ""
        self.out(f"\n{event.data['summary']}{' :' if preview else ''}")
        if preview:
            self._show_diff(preview)
        if self.__always:
            self.out("(autorisé : tu as répondu « toujours » dans cette session)", dim=True)
            granted: bool = True
        else:
            choice: str = self._choose("Autoriser ? [y] oui  [n] non  [a] toujours pour cette session  ", "yna")
            self.__always = choice == "a"
            granted = choice in "ya"
        self.__bus.dispatch(TOOL_GRANT_PERMISSION, id=event.data["id"], granted=granted)

    def _choose(self, question: str, choices: str) -> str:
        """ One of the letters of choices, typed after question: "n" for anything else """
        answer: str = self.ask(question).strip().lower()
        letter: str = "y" if answer[:1] == "o" else answer[:1]
        return letter if letter and letter in choices else "n"

    def __on_session_created(self, event: Event) -> None:
        """ Nouvelle session avec ton prompt système. """
        self.__always = False
        saved: str = "" if event.data["persistent"] else " (non enregistrée)"
        self.out(f"\nNouvelle session{saved}{' avec ton prompt système' if event.data['custom_prompt'] else ''}.\n")

    def __on_session_list(self, event: Event) -> None:
        """ One line per session: * for the current one, the folder when it is not this one """
        if not event.data["sessions"]:
            self.out(f"\nAucune session enregistrée pour {event.data['user']} : une session l'est dès ton premier message.\n")
            return
        lines: list[str] = [f"\nSessions de {event.data['user']} (* : en cours) :"]
        for session in event.data["sessions"]:
            where: str = "" if session["here"] else f"[{short_path(session['cwd'])}] "
            first: str = preview(session["first_message"]) if session["first_message"] else "(vide)"
            lines.append(f"{'*' if session['current'] else ' '} #{session['id']:<4} {where}{first}")
        self.out("\n".join(lines) + "\n")

    def __on_session_resumed(self, event: Event) -> None:
        """ The session resumed, with its last question and answer to remember where it was """
        self.__always = False
        lines: list[str] = [f"\nSession #{event.data['id']} reprise ({event.data['messages']} messages)."]
        if event.data["last_question"]:
            lines.append(f"  Toi   : {preview(event.data['last_question'])}")
        if event.data["last_answer"]:
            lines.append(f"  Louis : {preview(event.data['last_answer'])}")
        self.out("\n".join(lines) + "\n")

    def _on_structured(self, event: Event) -> None:
        """ The JSON of a reply that matches its schema, indented. One that does not is told by the end of the turn """
        if not event.data["valid"]:
            return
        self._newline()
        self.out(json.dumps(event.data["data"], ensure_ascii=False, indent=2))
        attempts: int = event.data["attempts"]
        self.out(f"(schéma {event.data['schema']}{f', {attempts} essais' if attempts > 1 else ''})", dim=True)

    def __on_schema_list(self, event: Event) -> None:
        """ One schema per line: its name for /json, what it is for, and where it comes from """
        folder: str = short_path(event.data["folder"])
        if not event.data["schemas"]:
            self.out(f"\nAucun schéma : ajoutes-en dans {folder}/ (un fichier <nom>.json par schéma).\n")
            return
        lines: list[str] = ["\nSchémas de /json <schéma> <question> :"]
        width: int = max(len(schema["name"]) for schema in event.data["schemas"])
        for schema in event.data["schemas"]:
            mark: str = "" if schema["ok"] else "⚠ "
            origin: str = " (projet)" if schema["origin"] == "projet" else ""
            lines.append(f"  {schema['name']:<{width}}  {mark}{preview(schema['description'] or '')}{origin}")
        lines.append(f"Les tiens vont dans {folder}/, ils passent avant ceux de Louis du même nom.")
        self.out("\n".join(lines) + "\n")

    def __on_command_unknown(self, event: Event) -> None:
        """ The commands there are, one per line, aligned """
        lines: list[str] = [f"\nCommande inconnue : /{event.data['name']}. Les commandes sont :"]
        for command in event.data["commands"]:
            lines.append(f"  {f'/{command['name']} {command['usage']}'.strip():18} {command['description']}")
        self.out("\n".join(lines) + "\n")

    def __on_command_error(self, event: Event) -> None:
        """ The message of the error, paths shortened """
        self.out(f"\n{event.data['message'].replace(os.path.expanduser('~') + os.sep, '~' + os.sep)}\n")

    def getUserInput(self):
        """ Get the user input from stdin """
        uin: str = self._read_line(self.promp)
        if not isinstance(uin, str):
            raise TypeError("User input doesnt seems to be an str")
        # readline() gives "" only at the end of the input (Ctrl+D): an empty line is "\n"
        if not uin:
            raise EOFError
        # The user pressed Enter: in a terminal, the cursor is back at the start of a line
        self.__at_line_start = True
        return uin

    def ask(self, question: str) -> str:
        """ Ask the user a question on stdin, the answer is empty at the end of the input """
        answer: str = self._read_line(question)
        self.__at_line_start = True
        return answer

    def out(self, content, *, end="\n", flush=False, dim=False):
        """ Print somthing, dim for what is less important (it goes to stderr in a plain terminal) """
        text: str = content + end
        self._write(text, dim=dim)
        if text:
            self.__at_line_start = text.endswith("\n")
        return self

    def debug(self, content):
        """ Print smth on stderr """
        self._write(content, dim=True)
        return self

    def _write(self, text: str, *, dim: bool = False) -> None:
        """ The one way the CLI draws: a plain terminal writes on stdout, or stderr for dim text """
        stream = sys.stderr if dim else sys.stdout
        stream.write(text)
        stream.flush()

    def _read_line(self, prompt: str) -> str:
        """ The one way the CLI reads: a line typed after prompt, "" at the end of the input """
        self._write(prompt)
        return sys.stdin.readline()
