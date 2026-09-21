##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Main file
##
import argparse
from settings import settings
from manager.manager import App

def parse_args() -> argparse.Namespace:
    """ Parse the command line arguments """
    parser = argparse.ArgumentParser(description="SENSAI")

    parser.add_argument("prompt", nargs="?", default=None, help="system prompt")
    parser.add_argument("--user", type=str, default="Anonymous", help="user name")
    return parser.parse_args()

def run(
        settings: dict[str],
        system_prompt: str | None = None,
        user: str = "Eratz"
    ) -> None:
    """ Run the CLI / Interface """
    manager: App = App(user, system_prompt=system_prompt)

    manager.run()

if __name__ == "__main__":
    args: argparse.Namespace = parse_args()

    run(settings, args.prompt, args.user)
