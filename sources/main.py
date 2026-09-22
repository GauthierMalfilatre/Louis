##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Main file
##
import argparse
from settings import settings
from manager.manager import App
from interface.web import WebInterface

def parse_args() -> argparse.Namespace:
    """ Parse the command line arguments """
    parser = argparse.ArgumentParser(description="KRONKAI")

    parser.add_argument("prompt", nargs="?", default=None, help="system prompt")
    parser.add_argument("--user", type=str, default="Anonymous", help="user name")
    parser.add_argument("--model", type=str, default=None, help="Model name")

    parser.add_argument("--web", action="store_true", help="chat from a browser instead of the terminal")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="web interface host")
    parser.add_argument("--port", type=int, default=8000, help="web interface port")
    return parser.parse_args()

def run(
        model: str | None,
        user: str,
        system_prompt: str | None,
        web: tuple[str, int] | None = None,
    ) -> None:
    """ Run the CLI, or the web interface when given its (host, port) """
    if web is None:
        App(model, user, system_prompt=system_prompt).run()
        return
    # The server stays up until run() returns, so the pages get the last messages
    with WebInterface(*web) as stream:
        App(model, user, system_prompt=system_prompt, stream=stream).run()

if __name__ == "__main__":
    args: argparse.Namespace = parse_args()
    run(args.model, args.user, args.prompt, (args.host, args.port) if args.web else None)
