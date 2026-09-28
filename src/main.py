##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Main file for the Sensai project
##
import sys
import os
from interface.interface import Interface
from interface.cli import CLI
from interface.cli_curses import CursesCLI
from app.app import App
from config.settings import settings
from config.prompt import SYSTEM_PROMPT
from logger.logger import log, setup_logger
from session.database import Database
from session.user import User, ANONYMOUS
from monitor.recorder import Recorder, traces_path
from monitor.report import report
import argparse

def parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Louis")

    parser.add_argument("--prompt", type=str, default=SYSTEM_PROMPT, help="system prompt")
    parser.add_argument("--user", type=str, default=ANONYMOUS, help=f"user name, whose sessions are saved (not {ANONYMOUS}'s)")
    parser.add_argument("--plain", action="store_true", help="plain terminal output, without the curses window")
    parser.add_argument("--dashboard", action="store_true", help="write the metrics of the recorded calls, open them, and quit")

    return parser.parse_args()

def run(system_prompt: str, username: str, plain: bool = False) -> int:
    """ Run the main programm by creating the Application and running it """

    db: Database | None = None
    try:
        if username and username != ANONYMOUS:
            db = Database(os.environ.get("LOUIS_DB") or os.path.join(os.getcwd(), settings["db.file"]))
            log.info(f"[session] database: {db.path}")
            user: User = User.get_or_create(db, username)
        else:
            user = User.anonymous()

        # The interface is chosen here: the app only talks to it through its event bus.
        # A curses window needs a real terminal: piped or redirected, Louis writes plain text
        terminal: bool = sys.stdin.isatty() and sys.stdout.isatty()
        interface: Interface = CursesCLI("> ") if terminal and not plain else CLI("> ")

        # Every call to the model and to the tools, for louis --dashboard
        monitor: Recorder = Recorder(traces_path(), settings)
        log.info(f"[monitor] traces: {monitor.path}")

        # Opened and closed around the whole run, even when it crashes
        with interface:
            app: App = App(settings, system_prompt, user, interface, monitor)
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

    if args.dashboard:
        sys.exit(report(traces_path(), open_browser=True))

    setup_logger()
    log.info(f"===== louis started in {os.getcwd()} =====")
    log.debug(f"[app] settings: {settings}")

    exitcode = run(args.prompt, args.user, args.plain)

    sys.exit(exitcode)
