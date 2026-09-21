#!/usr/bin/python
##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Main file
##
from interface.interface import CLI
from model.model import Model
from user.user import User
import sys
from settings import settings

def run(
        settings: dict[str],
        system_prompt: str | None = None
    ) -> None:
    """ Run the CLI / Interface """
    model : Model = Model("http://localhost:11434/api/chat", "qwen2.5-coder:7b")
    stream: CLI   = CLI("(you)$ ")
    user  : User  = User("Anonymous")

    user.stack(system_prompt, role="system")

    while True:
        try:
            userInput: str  = stream.get()
            response : dict = model.post(user, userInput, stream=settings["stream"])

            stream.out(user.history)
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

if __name__ == "__main__":
    prompt: str | None = None
    if len(sys.argv) >= 2:
        prompt = sys.argv[1]
    run(settings, prompt)
