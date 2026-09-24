##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /think: Toggle thinking mode
##
from command.command import Command
from events.event_list import THINKING_ENABLED, THINKING_DISABLED

class ToggleThinkCommand(Command):
    def __init__(self):
        super().__init__(
            "think",
            description="active ou désactive la réflexion du modèle (plus lent, meilleur sur les problèmes durs)",
        )

    def handle(self, app, arguments: str) -> None:
        """ Switch the thinking mode of the model on or off, for the next messages """
        if not app.model.thinking:
            self.error(app, "unsupported", f"Le modèle {app.model.model} ne sait pas réfléchir avant de répondre.",
                    model=app.model.model)
            return
        app.think = not app.think
        app.events.dispatch(THINKING_ENABLED if app.think else THINKING_DISABLED)
