##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /sessions: list the sessions of the user
##
from command.command import Command
from events.event_list import SESSION_LIST
import os

NOT_SAVED: str = ("Les sessions d'Anonymous ne sont pas enregistrées : lance louis avec --user <nom> "
                  "pour retrouver les tiennes.")

class SessionsCommand(Command):
    def __init__(self):
        super().__init__("sessions", description="liste tes sessions, avec leur premier message")

    def handle(self, app, arguments: str) -> None:
        """ Send the sessions of the user, oldest first, with their first message """
        if app.user.is_anonymous:
            self.error(app, "anonymous", NOT_SAVED)
            return
        here: str = os.getcwd()
        sessions: list[dict] = []
        for session in app.user.sessions:
            # Not saved yet, so still empty: nothing to come back to
            if not session.saved:
                continue
            sessions.append({
                "id"           : session.id,
                "first_message": session.first_user_message(),
                "cwd"          : session.cwd,
                "here"         : session.cwd == here,
                "current"      : session.id == app.session.id,
                "created_at"   : session.created_at,
            })
        app.events.dispatch(SESSION_LIST, user=app.user.name, sessions=sessions)
