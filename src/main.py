##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Main file for the Sensai project
##
import sys
from interface.cli import CLI
from app.app import App
from config.settings import settings
import argparse

def parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Louis")

    parser.add_argument("prompt", nargs="?", default="You are Louis, a helpfull AI assistant that always give short and clear responses.", help="system prompt")

    return parser.parse_args()

def run(system_prompt: str) -> int:
    """ Run the main programm by creating the Application and running it """

    app: App = App(settings, system_prompt)

    res = app.run()
    return res

if __name__ == "__main__":
    args: argparse.Namespace = parse()

    exitcode = run(args.prompt)

    sys.exit(exitcode)
