##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /react: Toggle the reasoning loop
##
from command.command import Command
from events.event_list import REASONING_ENABLED, REASONING_DISABLED

class ToggleReactCommand(Command):
    def __init__(self):
        super().__init__(
            "react",
            description="active ou désactive le raisonnement pas à pas, réponse vérifiée avant d'être donnée (plus lent)",
        )

    def handle(self, app, arguments: str) -> None:
        """ Switch the reasoning loop on or off, for the next messages """
        app.react = not app.react
        app.events.dispatch(REASONING_ENABLED if app.react else REASONING_DISABLED)
