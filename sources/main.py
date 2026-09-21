##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Main file
##

import requests
import json

from interface.interface import CLI
from model.model import Model
from user.user import User

def run() -> None:
    """ Run the CLI / Interface """
    model : Model = Model("http://localhost:11434/api/chat", "qwen2.5-coder:7b")
    stream: CLI   = CLI("(you)$ ")
    user  : User  = User("Anonymous")

    while True:
        try:
            userInput: str  = stream.get()
            response : dict = model.post(user, userInput)

            stream.out(response["message"]["content"])

        except KeyboardInterrupt:
            stream.out("\nGoodby...")
            break

if __name__ == "__main__":
    run()
