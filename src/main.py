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
from session.database import Database
from session.user import User, ANONYMOUS
import argparse

def parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Louis")

    parser.add_argument("--prompt", type=str, default=SYSTEM_PROMPT, help="system prompt")
    parser.add_argument("--user", type=str, default=ANONYMOUS, help=f"user name, whose sessions are saved (not {ANONYMOUS}'s)")

    return parser.parse_args()

def run(system_prompt: str, username: str) -> int:
    """ Run the main programm by creating the Application and running it """

    db: Database | None = None
    try:
        if username and username != ANONYMOUS:
            db = Database(os.environ.get("LOUIS_DB") or os.path.join(os.getcwd(), settings["db.file"]))
            log.info(f"[session] database: {db.path}")
            user: User = User.get_or_create(db, username)
        else:
            user = User.anonymous()

        app: App = App(settings, system_prompt, user)

        res = app.run()
    except Exception:
        log.exception("[app] crashed")
        raise
    finally:
        if db is not None:
            db.close()
    log.info("===== louis stopped =====")
    return res

if __name__ == "__main__":
    args: argparse.Namespace = parse()

    setup_logger()
    log.info(f"===== louis started in {os.getcwd()} =====")
    log.debug(f"[app] settings: {settings}")

    exitcode = run(args.prompt, args.user)

    sys.exit(exitcode)
