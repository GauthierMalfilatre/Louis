from commands.command import Command

class PongCommand(Command):
    def __init__(self):
        super().__init__("ping")

    def handler(self, content: str) -> bool:
        if content == "ping":
            print("pong")  # Change with stream.out()
            return True
        return False
