from commands.command import Command

class OpenSessionCommand(Command):
    def __init__(self):
        super().__init__("session", usage="<id>", description="Open one of your sessions")

    def handler(self, content: str, manager) -> bool:
        identifier: str = content.strip()
        if not identifier.isdigit():
            manager.stream.out("\nUsage: /session <id>\n")
            return True
        session = next(
            (session for session in manager.user.sessions if session.id == int(identifier)),
            None
        )
        if session is None:
            manager.stream.out(f"\nNo session {identifier}.\n")
            return True
        # SESSION_OPENED tells each interface, no need to print it here
        manager.session = session
        return True
