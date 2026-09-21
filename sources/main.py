##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Main file
##
from interface.interface import CLI
from model.model import Model
from user.user import User
from session.session import Session
from database.database import Database
import sys
from settings import settings

def run(
        settings: dict[str],
        system_prompt: str | None = None
    ) -> None:
    """ Run the CLI / Interface """
    model : Model = Model("http://localhost:11434/api/chat", "qwen2.5-coder:7b")
    db    : Database = Database(settings["db_path"])
    user  : User     = User.get_or_create(db, "Anonymous")
    stream: CLI      = CLI(f"({user.name})$ ")

    session: Session | None = user.last_session() if settings["resume"] else None
    if session is None:
        session = user.new_session(system_prompt)

    while True:
        try:
            userInput: str  = stream.get()
            response : dict = model.post(session, userInput, role=user.role, stream=settings["stream"])

            stream.out("")

            if settings["stream"]:
                for chunk in response:
                    stream.out(chunk, end="", flush=True)
                stream.out("\n")
            else:
                stream.out(response["message"]["content"] + "\n")

        except KeyboardInterrupt:
            stream.out("\nGoodby...")
            break

    db.close()

if __name__ == "__main__":
    prompt: str | None = None
    if len(sys.argv) >= 2:
        prompt = sys.argv[1]
    run(settings, prompt)
