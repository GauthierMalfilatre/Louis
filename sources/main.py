##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Main file
##
import sys
from settings import settings
from manager.manager import App

def run(
        settings: dict[str],
        system_prompt: str | None = None
    ) -> None:
    """ Run the CLI / Interface """
    manager: App = App("Eratz")

    manager.run()

if __name__ == "__main__":
    prompt: str | None = None
    if len(sys.argv) >= 2:
        prompt = sys.argv[1]
    run(settings, prompt)
