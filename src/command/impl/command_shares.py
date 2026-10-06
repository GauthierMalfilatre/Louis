##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /shares: list the public links of the user still open
##
from command.command import Command
from command.impl.command_share import ANONYMOUS
from events.event_list import SHARE_LIST
from share.store import shares

class SharesCommand(Command):
    def __init__(self):
        super().__init__("shares", description="liste tes liens publics encore ouverts")

    def handle(self, app, arguments: str) -> None:
        """ Send the open links of the user, newest first """
        if app.user.is_anonymous:
            self.error(app, "anonymous", ANONYMOUS)
            return
        app.events.dispatch(SHARE_LIST, user=app.user.name, shares=shares(app.user.db, app.user.id))
