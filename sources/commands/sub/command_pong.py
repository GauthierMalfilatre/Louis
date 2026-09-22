from commands.command import Command

class PongCommand(Command):
    def __init__(self):
        super().__init__("ping", description="Check that the app answers")

    def handler(self, content: str, manager) -> bool:
        manager.stream.out("pong")
        return True
