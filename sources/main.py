##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Main file
##

import requests
import json

from interface.Interface import CLI

def onReadCallback(input: str) -> str:
    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": "qwen2.5-coder:7b",
            "messages": [
                {
                    "role": "user",
                    "content": input
                }
            ],
            "stream": False
        }
    )
    data = response.json()
    return data["message"]["content"]


def run() -> None:
    """ Run the CLI / Interface """
    stream: CLI = CLI()
    stream.setCallback("onRead", onReadCallback)
    stream.setCallback("onDrain", print)
    stream.run()

if __name__ == "__main__":
    run()
