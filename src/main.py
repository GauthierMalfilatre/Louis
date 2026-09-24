##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Main file for the Sensai project
##
import sys
import os
from interface.cli import CLI
from app.app import App
from config.settings import settings
from config.prompt import SYSTEM_PROMPT
from logger.logger import log, setup_logger
import argparse

def parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Louis")

    parser.add_argument("--prompt", type=str, default=SYSTEM_PROMPT, help="system prompt")

    return parser.parse_args()

def run(system_prompt: str) -> int:
    """ Run the main programm by creating the Application and running it """

    try:
        app: App = App(settings, system_prompt)

        res = app.run()
    except Exception:
        log.exception("[app] crashed")
        raise
    log.info("===== louis stopped =====")
    return res

if __name__ == "__main__":
    args: argparse.Namespace = parse()

    setup_logger()
    log.info(f"===== louis started in {os.getcwd()} =====")
    log.debug(f"[app] settings: {settings}")

    exitcode = run(args.prompt)

    sys.exit(exitcode)
