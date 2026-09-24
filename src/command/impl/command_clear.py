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
        prompt: str = arguments.strip()
        session = app.new_session(prompt or None)
        number: str = f" #{session.id}" if session.id is not None else ""
        app.stream.out(f"\nNouvelle session{number}{' avec ton prompt système' if prompt else ''}.\n")
