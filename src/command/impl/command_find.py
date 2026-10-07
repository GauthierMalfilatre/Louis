##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /find: the sessions of the user that talked about something
##
from command.command import Command
from command.impl.command_sessions import NOT_SAVED
from events.event_list import SESSION_FOUND
from session.scribe import embedder
from session.search import find
import os

class FindCommand(Command):
    def __init__(self):
        super().__init__("find", description="retrouve tes sessions qui parlaient de quelque chose", usage="<texte>")

    def handle(self, app, arguments: str) -> None:
        """ The sessions about the text, by the meaning of their title and summary (the scribe's), or by its words """
        if app.user.is_anonymous:
            self.error(app, "anonymous", NOT_SAVED)
            return
        query: str = arguments.strip()
        if not query:
            self.error(app, "usage", "Usage : /find <texte>, par exemple /find lecture d'un fichier JSON.")
            return
        sessions, mode = find(app.user.db, app.user.id, query, embedder(app.settings), os.getcwd(), app.session.id)
        app.events.dispatch(SESSION_FOUND, user=app.user.name, query=query, mode=mode, sessions=sessions)
