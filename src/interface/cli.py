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
from events.event_list import TOOL_CALL_STARTED, TOOL_CALL_ENDED, APP_STOPPED, GUARD_TRIGGERED, EXPORT_DONE
from events.event_list import SHARE_CREATED, SHARE_LIST, SHARE_REVOKED, SESSION_FOUND
from datetime import datetime, timezone
from events.event_list import RAG_INDEXING, RAG_INDEX_PROGRESS, RAG_INDEXED, RAG_SOURCES, RAG_FORGOTTEN
from events.event_list import STRUCTURED_REPLY, SCHEMA_LIST
from events.event_list import RAG_DESCRIBE_PROGRESS
from events.event_list import REASONING_ENABLED, REASONING_DISABLED, REASONING_STEP, REASONING_CHECK, EVAL_REPORT
from events.event_list import PLAN_SETTINGS, PLAN_PROPOSED, PLAN_DECIDED
from events.event_list import MCP_STARTED, MCP_SERVERS
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
    "search_knowledge": "Connaissances",
    "git"       : "Git",
    "github_pr" : "Pull request",
}

# The formats of /export, as they are named to the user: the others in capitals (JSON)
FORMATS: dict[str, str] = {"md": "Markdown"}

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
    if name == "search_knowledge":
        where: str = f" dans {values['source']}" if values.get("source") else ""
        return f"« {shorten(values.get('query', ''))} »{where}"
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
    if name == "search_knowledge" and not lines[0].startswith("Aucun"):
        count = len(re.findall(r"^\[\d+\] ", result, re.MULTILINE))
        return f"{count} passage{'s' if count > 1 else ''}"
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

def thought_lines(thought: str) -> list[str]:
    """
        A thought of the reasoning loop as it is shown: its lines, without the Markdown bold nor the number the model
        sometimes gives its step itself, the interfaces number them
    """
    text: str = re.sub(r"^\s*(?:étape|step)\s*\d+\s*[:.)-]?\s*", "", thought.replace("**", ""), flags=re.IGNORECASE)
    return [line.strip() for line in text.splitlines() if line.strip()]

# The risk of an action of a plan, said to the user: what can not be undone stands out
RISKS: dict[str, str] = {"safe": "sans risque", "reversible": "réversible", "irreversible": "IRRÉVERSIBLE"}

def plan_title(action: dict) -> str:
    """ An action of a plan on one line, as its call is shown:  Modification /README.md """
    return f"{LABELS.get(action['tool'], action['tool'])} {call_detail(action['tool'], action['arguments'])}".rstrip()

def plan_details(action: dict) -> str:
    """ What an action would do, and how to undo it:  /README.md sera modifié · annulable : git restore README.md """
    undo: str = f"annulable : {action['undo']}" if action["undo"] else ""
    return " · ".join(part for part in (action["consequence"], undo) if part)

def plan_settings(data: dict) -> str:
    """ What /plan set, said to the user """
    if not data["enabled"]:
        return "Plan avant d'agir désactivé : chaque outil demande ton accord comme d'habitude. /plan on pour le remettre."
    which: str = ("seulement ce qui ne s'annule pas (un push, un merge, un fichier dont le contenu serait perdu)"
                  if data["level"] == "irreversible" else "toute action qui change quelque chose")
    return f"Plan avant d'agir activé, pour {which} : Louis te montre ce qu'il va faire et attend ton accord. /plan off pour le couper."

# How an MCP server goes, said to the user
MCP_STATES: dict[str, str] = {"running": "actif", "failed": "n'a pas démarré", "crashed": "s'est arrêté", "stopped": "arrêté"}

NO_MCP: str = "Aucun serveur MCP : déclare-les dans le réglage mcp.servers (voir le README)."

def mcp_started(servers: list[dict]) -> str:
    """ The MCP servers once Louis started them, on one line:  MCP : calc (1 outil) · time : n'a pas démarré (/mcp) """
    parts: list[str] = [
        f"{server['name']} ({len(server['tools'])} outil{'s' if len(server['tools']) > 1 else ''})"
        if server["state"] == "running" else f"{server['name']} : {MCP_STATES.get(server['state'], server['state'])}"
        for server in servers
    ]
    trouble: bool = any(server["state"] != "running" for server in servers)
    return f"MCP : {' · '.join(parts)}{' (/mcp pour savoir pourquoi)' if trouble else ''}"

def mcp_command(command: str, length: int = 60) -> str:
    """ How a server is launched, cut from its start if it is too long: its end (the script) says the most """
    return command if len(command) <= length else "…" + command[-(length - 1):]

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
        # "a" to a permission: that tool may act without asking, until the session changes. Only that one: an "a" to
        # an edit never lets a commit or a push go by unseen
        self.__always: set[str] = set()
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
        bus.subscribe(self._on_plan, PLAN_PROPOSED)
        bus.subscribe(self.__on_session_created, SESSION_CREATED)
        bus.subscribe(self.__on_session_list, SESSION_LIST)
        bus.subscribe(self.__on_session_resumed, SESSION_RESUMED)
        bus.subscribe(self.__on_session_found, SESSION_FOUND)
        bus.subscribe(self._on_structured, STRUCTURED_REPLY)
        bus.subscribe(self.__on_schema_list, SCHEMA_LIST)
        bus.subscribe(self.__on_export_done, EXPORT_DONE)
        bus.subscribe(self.__on_share_created, SHARE_CREATED)
        bus.subscribe(self.__on_share_list, SHARE_LIST)
        bus.subscribe(lambda event: self.out(f"\n✓ Lien fermé : {event.data['url']}\n"), SHARE_REVOKED)
        bus.subscribe(self.__on_command_unknown, COMMAND_UNKNOWN)
        bus.subscribe(self.__on_command_error, COMMAND_ERROR)
        bus.subscribe(self.__on_thinking_enabled, THINKING_ENABLED)
        bus.subscribe(self.__on_thinking_disabled, THINKING_DISABLED)
        bus.subscribe(self.__on_reasoning_enabled, REASONING_ENABLED)
        bus.subscribe(self.__on_reasoning_disabled, REASONING_DISABLED)
        bus.subscribe(self._on_reasoning_step, REASONING_STEP)
        bus.subscribe(self._on_reasoning_check, REASONING_CHECK)
        bus.subscribe(self.__on_plan_settings, PLAN_SETTINGS)
        bus.subscribe(self.__on_guard, GUARD_TRIGGERED)
        bus.subscribe(self.__on_rag_indexing, RAG_INDEXING)
        bus.subscribe(self.__on_rag_progress, RAG_INDEX_PROGRESS)
        bus.subscribe(self.__on_rag_described, RAG_DESCRIBE_PROGRESS)
        bus.subscribe(self.__on_rag_indexed, RAG_INDEXED)
        bus.subscribe(self.__on_rag_sources, RAG_SOURCES)
        bus.subscribe(self.__on_rag_forgotten, RAG_FORGOTTEN)
        bus.subscribe(self.__on_eval_report, EVAL_REPORT)
        bus.subscribe(self.__on_mcp_started, MCP_STARTED)
        bus.subscribe(self.__on_mcp_servers, MCP_SERVERS)
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
        if event.data.get("summarized"):
            parts.append("résumés par le modèle")
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

    def __on_reasoning_enabled(self, event: Event) -> None:
        """ Say the replies will be slower, and what is shown of them """
        self.out("\nRaisonnement pas à pas activé : Louis dit ce qu'il fait à chaque étape et vérifie sa réponse avant "
                 "de la donner, c'est plus long. /react pour le couper.\n")

    def __on_reasoning_disabled(self, event: Event) -> None:
        """ Back to the usual replies """
        self.out("\nRaisonnement pas à pas désactivé : Louis répond comme d'habitude.\n")

    def __on_plan_settings(self, event: Event) -> None:
        """ Whether the plans are shown, and for which actions """
        self.out(f"\n{plan_settings(event.data)}\n")

    def _on_reasoning_step(self, event: Event) -> None:
        """
            A step of the reasoning loop, dim, on its own line: its number and what the model thinks before it acts,
            its tool calls below it. A draft is only said to be written: its check comes next, the answer once checked
        """
        self._newline()
        lines: list[str] = thought_lines(event.data["thought"])
        if not event.data["tools"]:
            lines = ["réponse écrite"] + lines
        if lines:
            self.out(f"  ⟳ Étape {event.data['step']} : {lines[0]}" + "".join(f"\n      {line}" for line in lines[1:]),
                     dim=True)

    def _on_reasoning_check(self, event: Event) -> None:
        """
            What the check of the draft found, dim: ✔ when it goes, ✘ when it is written again, ⚠ when it is given with
            problems left (the attempts are spent). The problems follow, one per line
        """
        self._newline()
        data: dict = event.data
        if data["ok"]:
            self.out(f"  ✔ Réponse vérifiée{f' (vérification {data["attempt"]})' if data['attempt'] > 1 else ''}", dim=True)
            return
        what: str = "à corriger" if data["revise"] else "problèmes restants, réponse donnée quand même"
        self.out(f"  {'✘' if data['revise'] else '⚠'} Vérification {data['attempt']} : {what}"
                 + "".join(f"\n      - {problem}" for problem in data["problems"]), dim=True)

    def __on_guard(self, event: Event) -> None:
        """ What the guard changed, dim, before the reply or the refusal:  ⛨ Message anonymisé : … """
        self._newline()
        before: bool = event.data["stage"] == "input"
        if event.data["stage"] == "tool_call":
            # Under the call, before its result:  ⎿ refusé
            self.out(f"    ⛨ Appel bloqué par le garde-fou ({', '.join(event.data['rails'])})", dim=True)
        elif event.data["stage"] == "tool_result":
            # Under the call too: what it gave, filtered before the model reads it
            self.out("    ⛨ Résultat filtré par le garde-fou (passages piégés retirés, données sensibles masquées)", dim=True)
        elif event.data["action"] == "refused":
            what: str = "Message bloqué" if before else "Réponse bloquée"
            self.out(f"⛨ {what} par le garde-fou ({', '.join(event.data['rails'])})", dim=True)
        elif before:
            # The user sees what the model reads in place of the message
            self.out(f"⛨ Message anonymisé avant le modèle : {preview(event.data['content'])}", dim=True)
        else:
            self.out("⛨ Réponse anonymisée par le garde-fou", dim=True)

    def __on_rag_indexing(self, event: Event) -> None:
        """ Tell the folder is being read: embedding a big one takes minutes """
        self.out(f"\nIndexation de {short_path(event.data['root'])} ({event.data['files']} fichiers), Ctrl+C pour arrêter…")

    def __on_rag_progress(self, event: Event) -> None:
        """ How far it is, dim:   … 300/2000 fichiers """
        self.out(f"  … {event.data['done']}/{event.data['total']} fichiers", dim=True)

    def __on_rag_described(self, event: Event) -> None:
        """ A file described: the model takes seconds a passage, the user sees it moving, dim """
        data: dict = event.data
        self.out(f"  … {short_path(data['path'])} décrit ({data['described']} passages décrits, "
                 f"{data['reused']} repris, {data['seconds']:.0f}s)", dim=True)

    def __on_rag_indexed(self, event: Event) -> None:
        """ What the folder gave: the source, its files, its passages, and if the search by meaning works on them """
        data: dict = event.data
        lines: list[str] = [
            f"Source « {data['source']} » à jour : {data['files']} fichiers ({data['updated']} lus, {data['unchanged']} "
            f"inchangés, {data['removed']} retirés, {data['skipped']} ignorés), {data['chunks']} passages · {data['duration']:.1f}s"
        ]
        if data["chunks"] and data["embedded"] < data["chunks"]:
            lines.append(f"  Recherche par mots-clés seulement pour {data['chunks'] - data['embedded']} passages : "
                         f"{data['warning'] or "aucun modèle d'embedding"}. Relance /index quand il répond.")
        if data.get("excluded"):
            lines.append(f"  {data['excluded']} fichiers exclus par {', '.join(data['exclude'])}.")
        if data.get("describe"):
            lines.append(f"  Code décrit : {data['described']} passages par le modèle ({data['describe_seconds']:.0f}s), "
                         f"{data['reused']} repris des descriptions déjà faites.")
            if data.get("describe_warning"):
                lines.append(f"  Le reste sans description : {data['describe_warning']}. Relance /index quand il répond.")
        made: list[dict] = data.get("generated") or []
        if made:
            # Left out without being asked: the user must see which, and how to keep one
            lines.append(f"  Laissés de côté, générés par un programme ({len(made)}) :")
            lines.extend(f"    {item['path']} ({item['reason']})" for item in made[:5])
            if len(made) > 5:
                lines.append(f"    … et {len(made) - 5} autres")
            lines.append("  Pour en garder : réglage rag.index.generated_ratio (0 : seulement ceux marqués « @generated »).")
        self.out("\n".join(lines) + "\n")

    def __on_rag_sources(self, event: Event) -> None:
        """ One line per source, its folder and how many passages it holds """
        if not event.data["sources"]:
            self.out("\nLa base de connaissances est vide : /index <dossier> y met de la documentation ou du code.\n")
            return
        lines: list[str] = [f"\nBase de connaissances ({len(event.data['sources'])} sources) :"]
        for source in event.data["sources"]:
            words: str = "" if source["embedded"] == source["chunks"] else "  (mots-clés seulement)"
            excluded: str = f"  sans {', '.join(source['exclude'])}" if source.get("exclude") else ""
            described: str = "  (code décrit)" if source.get("describe") else ""
            lines.append(f"  {source['name']:16} {source['files']:>6} fichiers {source['chunks']:>7} passages  "
                         f"[{short_path(source['root'])}]{words}{described}{excluded}")
        self.out("\n".join(lines) + "\n")

    def __on_rag_forgotten(self, event: Event) -> None:
        """ The source removed """
        self.out(f"\nSource « {event.data['source']} » retirée ({event.data['chunks']} passages).\n")

    def __on_mcp_started(self, event: Event) -> None:
        """ The MCP servers on one line: dim while they all run, plain when one did not start """
        servers: list[dict] = event.data["servers"]
        self.out(mcp_started(servers), dim=all(server["state"] == "running" for server in servers))

    def __on_mcp_servers(self, event: Event) -> None:
        """ Each server with its state and how it is launched, why it does not answer, then its tools and their risk """
        servers: list[dict] = event.data["servers"]
        if not servers:
            self.out(f"\n{NO_MCP}\n")
            return
        lines: list[str] = [f"\nServeurs MCP ({len(servers)}) :"]
        for server in servers:
            lines.append(f"  {server['name']:12} {MCP_STATES.get(server['state'], server['state']):16} "
                         f"[{mcp_command(server['command'])}]")
            if server["error"]:
                lines.append(f"    {server['error']}")
            for tool in server["tools"]:
                lines.append(f"    {tool['name']:32} {RISKS.get(tool['risk'], tool['risk']):12} "
                             f"{shorten(tool['description'], PREVIEW_LENGTH)}")
        self.out("\n".join(lines) + "\n")

    def __on_permission(self, event: Event) -> None:
        """ Show what a tool wants to do and its diff, then grant it if the user agrees, or always agrees """
        preview: str = event.data.get("preview") or ""
        self.out(f"\n{event.data['summary']}{' :' if preview else ''}")
        if preview:
            self._show_diff(preview)
        tool: str = event.data["tool"]
        if event.data.get("every_time"):
            # Asked each time: "always" is for the tools, never for this
            granted: bool = self._choose("Confirmer ? [y] oui  [n] non  ", "yn") == "y"
        elif tool in self.__always:
            self.out(f"(autorisé : tu as répondu « toujours » pour {tool} dans cette session)", dim=True)
            granted = True
        else:
            choice: str = self._choose(f"Autoriser ? [y] oui  [n] non  [a] toujours pour {tool} dans cette session  ", "yna")
            if choice == "a":
                self.__always.add(tool)
            granted = choice in "ya"
        self.__bus.dispatch(TOOL_GRANT_PERMISSION, id=event.data["id"], granted=granted)

    def _on_plan(self, event: Event) -> None:
        """
            The plan of a reply that would do something risky, before any of its calls runs: what the model meant,
            then each action numbered with its risk, what it would do, how to undo it and what it would change. The
            user approves it, refuses it, or answers what they would rather have, given to the model
        """
        data: dict = event.data
        self._newline()
        intent: list[str] = thought_lines(data["intent"])
        self.out(f"\nMon plan : {intent[0]}" if intent else "\nAvant d'agir, voici ce que je vais faire :")
        for line in intent[1:]:
            self.out(f"  {line}")
        for number, action in enumerate(data["actions"], 1):
            self.out(f"  {number}. {plan_title(action)} · {RISKS.get(action['risk'], action['risk'])}")
            if details := plan_details(action):
                self.out(f"     {details}", dim=True)
            if action["preview"]:
                self._show_diff(action["preview"])
        choice: str = self._choose("Approuver ce plan ? [y] oui  [n] non  [r] répondre  ", "ynr")
        feedback: str = self.ask("Ta réponse : ").strip() if choice == "r" else ""
        approved: bool = choice == "y"
        self.out("(plan approuvé : j'y vais)" if approved else "(plan refusé : je ne fais rien de tout ça)", dim=True)
        self.__bus.dispatch(PLAN_DECIDED, id=data["id"], approved=approved, feedback=feedback)

    def _choose(self, question: str, choices: str) -> str:
        """ One of the letters of choices, typed after question: "n" for anything else """
        answer: str = self.ask(question).strip().lower()
        letter: str = "y" if answer[:1] == "o" else answer[:1]
        return letter if letter and letter in choices else "n"

    def __on_session_created(self, event: Event) -> None:
        """ Nouvelle session avec ton prompt système. """
        self.__always.clear()
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
            first: str = preview(session.get("title") or session["first_message"] or "(vide)")
            lines.append(f"{'*' if session['current'] else ' '} #{session['id']:<4} {where}{first}")
        self.out("\n".join(lines) + "\n")

    def __on_session_found(self, event: Event) -> None:
        """ The sessions found, the closest first: their title (or first message), then their summary """
        sessions: list[dict] = event.data["sessions"]
        if not sessions:
            self.out(f"\nAucune session ne parle de « {event.data['query']} ».\n")
            return
        how: str = "par le sens" if event.data["mode"] == "meaning" else "par les mots"
        lines: list[str] = [f"\nSessions sur « {event.data['query']} » ({how}, /resume <id> pour en reprendre une) :"]
        for session in sessions:
            where: str = "" if session["here"] else f"[{short_path(session['cwd'])}] "
            lines.append(f"{'*' if session['current'] else ' '} #{session['id']:<4} {where}"
                         f"{preview(session['title'] or session['first_message'] or '(vide)')}")
            if session["summary"]:
                lines.append(f"        {preview(session['summary'])}")
        self.out("\n".join(lines) + "\n")

    def __on_session_resumed(self, event: Event) -> None:
        """ The session resumed, with its last question and answer to remember where it was """
        self.__always.clear()
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

    def __on_eval_report(self, event: Event) -> None:
        """
            The scores of the last answer (/eval), then the claims its sources do not support:
              ✗ contredite   « ... »  [2] cat_file {"path": "src/app.py"} : « the passage »
              ? invérifiable « ... »
        """
        data: dict = event.data
        self._newline()
        if data["status"] != "ok":
            self.out(f"⚖ Le juge ({data['judge']}) n'a pas pu évaluer la dernière réponse : {data['error']}\n")
            return
        claims: list[dict] = data["claims"]
        supported: int = sum(1 for claim in claims if claim["verdict"] == "supported")
        sources: int = len(data["sources"])
        if data["faithfulness"] is not None:
            faithful: str = (f"{round(data['faithfulness'] * 100)} %  ({supported} affirmation{'s' if supported > 1 else ''}"
                             f" sur {len(claims)} appuyée{'s' if supported > 1 else ''} par {sources} source{'s' if sources > 1 else ''})")
        else:
            faithful = "aucune source lue : réponse de mémoire" if not sources else "aucun fait à vérifier"
        spent: dict = data["spent"]
        detail: str = f", dont {spent['generation']:.0f} s à écrire {spent['completion_tokens']} tokens"
        if spent["load"] >= 1.0:
            detail += f" et {spent['load']:.0f} s à recharger le modèle"
        self.out(f"⚖ Dernière réponse, notée par {data['judge']} en {data['duration']:.1f} s{detail}")
        self.out(f"  fidélité aux sources  {faithful}")
        self.out(f"  pertinence            {data['relevance']}/5  {data['relevance_reason']}", dim=True)
        self.out(f"  cohérence             {data['coherence']}/5  {data['coherence_reason']}", dim=True)
        labels: dict[str, str] = {"contradicted": "✗ contredite  ", "unverifiable": "? invérifiable"}
        for claim in sorted((c for c in claims if c["verdict"] != "supported"), key=lambda c: c["verdict"] != "contradicted"):
            self.out(f"  {labels[claim['verdict']]} « {claim['text']} »")
            if claim["source"]:
                source: dict = data["sources"][claim["source"] - 1]
                where: str = f"[{claim['source']}] {LABELS.get(source['tool'], source['tool'])} {call_detail(source['tool'], source['arguments'])}"
                quote: str = f" : « {shorten(claim['evidence'], PREVIEW_LENGTH)} »" if claim["evidence"] else ""
                self.out(f"      {where}{quote}{'' if claim['quoted'] or not claim['evidence'] else ' (citation introuvable dans la source)'}", dim=True)
            elif claim["reason"]:
                self.out(f"      {claim['reason']}", dim=True)
        self.out("")

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

    def __on_export_done(self, event: Event) -> None:
        """
            ✓ Session #12 exportée en JSON (8 messages, 1 fichier) : ~/projet/exports/session-12.json
            ✓ /pendu.py (session #12) exporté en Markdown : ~/projet/exports/session-12-pendu.py.md
            ✓ 3 fichiers (session #12) exportés en Markdown : ~/projet/exports/session-12-fichiers.md
        """
        which: str = f"session #{event.data['id']}" if event.data["id"] is not None else "session"
        path: str = event.data["path"].replace(os.path.expanduser("~") + os.sep, "~" + os.sep)
        shown: str = FORMATS.get(event.data["format"], event.data["format"].upper())
        files: list[str] | None = event.data.get("files")
        if files:
            what: str = files[0] if len(files) == 1 else f"{len(files)} fichiers"
            self.out(f"\n✓ {what} ({which}) exporté{'s' if len(files) > 1 else ''} en {shown} : {path}\n")
            return
        count, files = event.data["messages"], event.data.get("artifacts", 0)
        written: str = f", {files} fichier{'s' if files > 1 else ''}" if files else ""
        self.out(f"\n✓ {which.capitalize()} exportée en {shown} ({count} message{'s' if count > 1 else ''}{written}) : {path}\n")

    def __on_share_created(self, event: Event) -> None:
        """ ✓ Lien public de la session #12 : http://…/s/Xk3f9QaL…, and how to close it """
        what: str = (f"de {event.data['title']} (session #{event.data['id']})" if event.data["kind"] == "artifact"
                     else f"de la session #{event.data['id']}")
        lines: list[str] = [f"\n✓ Lien public {what} : {event.data['url']}"]
        if event.data["masked"]:
            lines.append(f"  {event.data['masked']} texte{'s' if event.data['masked'] > 1 else ''} masqué"
                         f"{'s' if event.data['masked'] > 1 else ''} (données sensibles).")
        lines.append(f"  /unshare {event.data['token'][:8]} pour le fermer.")
        self.out("\n".join(lines) + "\n")

    def __on_share_list(self, event: Event) -> None:
        """ One link per line: the start of its token (for /unshare), its session, when, its title, then its address """
        if not event.data["shares"]:
            self.out(f"\nAucun lien public ouvert pour {event.data['user']} : /share pour en créer un.\n")
            return
        lines: list[str] = [f"\nLiens publics de {event.data['user']} (/unshare <jeton> pour en fermer un) :"]
        for share in event.data["shares"]:
            try:
                # Saved in UTC: shown in the time of the user
                when: str = datetime.strptime(share["created_at"], "%Y-%m-%d %H:%M:%S") \
                    .replace(tzinfo=timezone.utc).astimezone().strftime("%d/%m %H:%M")
            except (TypeError, ValueError):
                when = share["created_at"] or ""
            session: str = f"#{share['session_id']}" if share["session_id"] is not None else "–"
            lines.append(f"  {share['token'][:8]}  {session:<5} {when}  {preview(share['title'] or '(sans titre)')}")
            lines.append(f"            {share['url']}")
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
