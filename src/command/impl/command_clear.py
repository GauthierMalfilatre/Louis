##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /clear: start a new session
##
from command.command import Command

class ClearCommand(Command):
    def __init__(self):
        super().__init__(
            "clear",
            description="nouvelle session, avec ce prompt système s'il est donné",
            usage="[prompt]"
        )

    def handle(self, app, arguments: str) -> None:
        """ Start a new session, on the system prompt given or on the one Louis started with """
        # The app tells the interfaces with SESSION_CREATED, as for every new session
        app.new_session(arguments.strip() or None)
