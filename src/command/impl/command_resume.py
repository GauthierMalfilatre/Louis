##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /resume: go back to a session
##
from command.command import Command
from command.impl.command_sessions import NOT_SAVED
from config.prompt import NUDGE_PROMPT
from events.event_list import SESSION_RESUMED
from logger.logger import log
import os

class ResumeCommand(Command):
    def __init__(self):
        super().__init__("resume", description="reprend la session <id>, là où elle s'était arrêtée", usage="<id>")

    def handle(self, app, arguments: str) -> None:
        """ Make a session of the user the current one again, if it was held in this folder """
        if app.user.is_anonymous:
            self.error(app, "anonymous", NOT_SAVED)
            return
        identifier: str = arguments.strip().removeprefix("#")
        if not identifier.isdigit():
            self.error(app, "usage", "Usage : /resume <id>, avec un id donné par /sessions.")
            return
        session_id: int = int(identifier)
        if session_id == app.session.id:
            self.error(app, "current", f"La session #{session_id} est déjà en cours.", id=session_id)
            return
        session = app.user.get_session(session_id)
        if session is None:
            self.error(app, "not_found", f"Tu n'as pas de session #{session_id} : tape /sessions pour les voir.",
                       id=session_id)
            return
        # The tools work in the folder Louis runs in: the files of the session are elsewhere
        if session.cwd != os.getcwd():
            self.error(app, "elsewhere", f"La session #{session_id} a eu lieu dans {session.cwd} : "
                                         "lance louis dans ce dossier pour la reprendre.",
                       id=session_id, cwd=session.cwd)
            return

        app.user.current_session = session
        log.info(f"[session] resumed #{session_id} of {app.user.name}")
        messages = session.messages
        app.events.dispatch(
            SESSION_RESUMED,
            id=session_id,
            user=app.user.name,
            messages=len(messages),
            last_question=next(
                (m.content for m in reversed(messages) if m.role == "user" and m.content != NUDGE_PROMPT), None
            ),
            last_answer=next((m.content for m in reversed(messages) if m.role == "assistant" and m.content.strip()), None)
        )
