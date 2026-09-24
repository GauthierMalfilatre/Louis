##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /sessions: list the sessions of the user
##
from command.command import Command
import os

PREVIEW_LENGTH = 70

NOT_SAVED: str = ("\nLes sessions d'Anonymous ne sont pas enregistrées : lance louis avec --user <nom> "
                "pour retrouver les tiennes.\n")

def preview(text: str) -> str:
    """ A message on one line, cut if it is too long """
    text = " ".join(text.split())
    return text if len(text) <= PREVIEW_LENGTH else text[:PREVIEW_LENGTH - 1] + "…"

def short_path(path: str) -> str:
    """ A path, with ~ for the home folder """
    home: str = os.path.expanduser("~")
    return "~" + path[len(home):] if path == home or path.startswith(home + os.sep) else path

class SessionsCommand(Command):
    def __init__(self):
        super().__init__("sessions", description="liste tes sessions, avec leur premier message")

    def handle(self, app, arguments: str) -> None:
        """ Show the id and the first message of every session, the current one marked with * """
        if app.user.is_anonymous:
            app.stream.out(NOT_SAVED)
            return
        lines: list[str] = []
        for session in app.user.sessions:
            current: bool = session.id == app.session.id
            first: str | None = session.first_user_message()
            # Started, then left without a word: nothing to come back to
            if first is None and not current:
                continue
            where: str = "" if session.cwd == os.getcwd() else f"[{short_path(session.cwd)}] "
            lines.append(f"{'*' if current else ' '} #{session.id:<4} {where}{preview(first) if first else '(vide)'}")
        app.stream.out(f"\nSessions de {app.user.name} (* : en cours) :\n" + "\n".join(lines) + "\n")
