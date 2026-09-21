from commands.command import Command
from session.session import Session

class NewSessionCommand(Command):
    def __init__(self):
        super().__init__("new-session")

    def handler(self, content: str, manager) -> bool:
        manager.session = manager.user.new_session(content)
        manager.stream.out("\nNew session started.\n")
        return True
