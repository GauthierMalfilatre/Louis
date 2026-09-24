##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /resume: go back to a session
##
from command.command import Command
from command.impl.command_sessions import NOT_SAVED, preview, short_path
from config.prompt import NUDGE_PROMPT
from logger.logger import log
import os

class ResumeCommand(Command):
    def __init__(self):
        super().__init__("resume", description="reprend la session <id>, là où elle s'était arrêtée", usage="<id>")

    def handle(self, app, arguments: str) -> None:
        """ Make a session of the user the current one again, if it was held in this folder """
        if app.user.is_anonymous:
            app.stream.out(NOT_SAVED)
            return
        identifier: str = arguments.strip().removeprefix("#")
        if not identifier.isdigit():
            app.stream.out("\nUsage : /resume <id>, avec un id donné par /sessions.\n")
            return
        session_id: int = int(identifier)
        if session_id == app.session.id:
            app.stream.out(f"\nLa session #{session_id} est déjà en cours.\n")
            return
        session = app.user.get_session(session_id)
        if session is None:
            app.stream.out(f"\nTu n'as pas de session #{session_id} : tape /sessions pour les voir.\n")
            return
        # The tools work in the folder Louis runs in: the files of the session are elsewhere
        if session.cwd != os.getcwd():
            app.stream.out(f"\nLa session #{session_id} a eu lieu dans {short_path(session.cwd)} : "
                            "lance louis dans ce dossier pour la reprendre.\n")
            return

        app.user.current_session = session
        log.info(f"[session] resumed #{session_id} of {app.user.name}")
        messages = session.messages
        asked: str | None = next(
            (m.content for m in reversed(messages) if m.role == "user" and m.content != NUDGE_PROMPT), None
        )
        answered: str | None = next((m.content for m in reversed(messages) if m.role == "assistant" and m.content.strip()), None)
        recap: str = f"\nSession #{session_id} reprise ({len(messages)} messages)."
        if asked:
            recap += f"\n  Toi   : {preview(asked)}"
        if answered:
            recap += f"\n  Louis : {preview(answered)}"
        app.stream.out(recap + "\n")
