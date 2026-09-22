from commands.command import Command
from session.session import Session

class NewModelCommand(Command):
    def __init__(self):
        super().__init__("model")

    def handler(self, content: str, manager) -> bool:
        manager.stream.out("\nSwitching to new model...\n")
        manager.session = manager.model.switch(newmodel=content)
        manager.stream.out(f"New model {manager.model.model}\n")
        return True
