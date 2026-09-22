from commands.command import Command

class NewModelCommand(Command):
    def __init__(self):
        super().__init__("model", usage="<name>", description="Switch to another model")

    def handler(self, content: str, manager) -> bool:
        manager.stream.out("\nSwitching to new model...\n")
        manager.model = content
        manager.stream.out(f"New model {manager.model.model}\n")
        return True
