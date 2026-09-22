from commands.command import Command

class ExitCommand(Command):
    def __init__(self):
        super().__init__("exit", description="End the session and quit")

    def handler(self, content: str, manager) -> bool:
        manager.stream.close()
        return True
