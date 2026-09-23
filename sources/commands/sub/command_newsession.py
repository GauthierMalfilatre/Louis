from commands.command import Command
from session.session import Session

class NewSessionCommand(Command):
    def __init__(self):
        super().__init__("new-session", usage="[system prompt]", description="Start a new conversation")

    def handler(self, content: str, manager) -> bool:
        # SESSION_OPENED tells each interface, no need to print it here
        manager.session = manager.user.new_session(content)
        return True
