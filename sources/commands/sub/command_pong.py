from commands.command import Command

class PongCommand(Command):
    def __init__(self):
        super().__init__("ping")

    def handler(self, content: str, manager) -> bool:
        manager.stream.out("pong")
        return True
