##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Main file
##

import requests
import json

from sources.interface.interface import CLI
from model.model import Model

def run() -> None:
    """ Run the CLI / Interface """
    model : Model = Model("http://localhost:11434/api/chat", "qwen2.5-coder:7b")
    stream: CLI   = CLI("(you)$ ")

    while True:
        try:
            userInput: str = stream.get()

            response = model.post(None, userInput)

            stream.out(response["message"]["content"])

        except KeyboardInterrupt:
            stream.out("Exiting")
            break

if __name__ == "__main__":
    run()
