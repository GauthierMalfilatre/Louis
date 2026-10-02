from bootstrap.sources.commands.command import Command

class NewModelCommand(Command):
    def __init__(self):
        super().__init__("model", usage="<name>", description="Switch to another model")

    def handler(self, content: str, manager) -> bool:
        # The switch itself dispatches MODEL_SWITCHED: each interface shows it its own way
        manager.model = content
        return True
