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
from events.event_list import TOOL_BEGFOR_PERMISSION, TOOL_GRANT_PERMISSION
import os
import sys

PREVIEW_LENGTH = 70

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
        super().__init__()

    @property
    def promp(self) -> str:
        """ Get the prompt of the CLI """
        return self.__prompt

    def bind(self, bus: EventBus) -> "CLI":
        """ Show the sessions and the results of the commands as text, and ask the permissions """
        # Kept to answer: a permission is granted by dispatching TOOL_GRANT_PERMISSION
        self.__bus: EventBus = bus
        bus.subscribe(self.__on_permission, TOOL_BEGFOR_PERMISSION)
        bus.subscribe(self.__on_session_created, SESSION_CREATED)
        bus.subscribe(self.__on_session_list, SESSION_LIST)
        bus.subscribe(self.__on_session_resumed, SESSION_RESUMED)
        bus.subscribe(self.__on_command_unknown, COMMAND_UNKNOWN)
        bus.subscribe(self.__on_command_error, COMMAND_ERROR)
        return self

    def __on_permission(self, event: Event) -> None:
        """ Show what a tool wants to do and its diff, then grant it if the user agrees """
        preview: str = event.data.get("preview") or ""
        self.out(f"\n{event.data['summary']}{' :' if preview else ''}")
        if preview:
            self.out(preview)
        answer: str = self.ask("Autoriser ? [y/n] ")
        self.__bus.dispatch(
            TOOL_GRANT_PERMISSION,
            id=event.data["id"],
            granted=answer.strip().lower() in ("o", "oui", "y", "yes")
        )

    def __on_session_created(self, event: Event) -> None:
        """ Nouvelle session avec ton prompt système. """
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
        lines: list[str] = [f"\nSession #{event.data['id']} reprise ({event.data['messages']} messages)."]
        if event.data["last_question"]:
            lines.append(f"  Toi   : {preview(event.data['last_question'])}")
        if event.data["last_answer"]:
            lines.append(f"  Louis : {preview(event.data['last_answer'])}")
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
        self.out(self.promp, end="", flush=True)
        uin: str = sys.stdin.readline()
        if not isinstance(uin, str):
            raise TypeError("User input doesnt seems to be an str")
        # readline() gives "" only at the end of the input (Ctrl+D): an empty line is "\n"
        if not uin:
            raise EOFError
        return uin

    def ask(self, question: str) -> str:
        """ Ask the user a question on stdin, the answer is empty at the end of the input """
        self.out(question, end="", flush=True)
        return sys.stdin.readline()

    def out(self, content, *, end="\n", flush=False):
        """ Print somthing on the stdout """
        sys.stdout.write(content + end)
        if flush:
            sys.stdout.flush()
        return self

    def debug(self, content):
        """ Print smth on stderr """
        sys.stderr.write(content)
        return self
