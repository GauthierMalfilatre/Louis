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
from interface.quiet import QuietInterface
from app.app import App
from config.settings import settings
from config.prompt import SYSTEM_PROMPT
from logger.logger import log, setup_logger
from session.database import Database
from session.user import User, ANONYMOUS
from monitor.recorder import Recorder, traces_path
from monitor.report import report
from model.model_exception import ModelException
from structured.schema import load, SchemaError
import argparse
import json

def parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Louis")

    parser.add_argument("--prompt", type=str, default=SYSTEM_PROMPT, help="system prompt")
    parser.add_argument("--user", type=str, default=ANONYMOUS, help=f"user name, whose sessions are saved (not {ANONYMOUS}'s)")
    parser.add_argument("--plain", action="store_true", help="plain terminal output, without the curses window")
    parser.add_argument("--dashboard", action="store_true", help="write the metrics of the recorded calls, open them, and quit")
    parser.add_argument("--schema", type=str, help="with --ask: name or file of the JSON Schema the reply must match")
    parser.add_argument("--ask", type=str, help="with --schema: answer this question with JSON only, print it and quit "
                                                 "(text piped in is added to the question)")

    args: argparse.Namespace = parser.parse_args()
    if (args.schema is None) != (args.ask is None):
        parser.error("--schema and --ask go together: louis --schema <schema> --ask \"<question>\"")
    return args

def open_user(username: str) -> tuple[Database | None, User]:
    """ The user Louis talks to, with the database its sessions are saved in (None for the anonymous one) """
    if not username or username == ANONYMOUS:
        return None, User.anonymous()
    db: Database = Database(os.environ.get("LOUIS_DB") or os.path.join(os.getcwd(), settings["db.file"]))
    log.info(f"[session] database: {db.path}")
    return db, User.get_or_create(db, username)

def run(system_prompt: str, username: str, plain: bool = False) -> int:
    """ Run the main programm by creating the Application and running it """

    db: Database | None = None
    try:
        db, user = open_user(username)

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

def ask(system_prompt: str, username: str, schema_name: str, question: str) -> int:
    """
        Answer one question with JSON that matches the schema, for a script: stdout is the JSON alone, the errors go
        to stderr. Text piped in (cat notes.txt | louis ...) is added to the question: the model has no tool to read
        a file. 0 when the reply matches, 1 when it does not or the model fails, 2 for a schema that can not be used
    """
    try:
        name, schema = load(schema_name)
    except SchemaError as e:
        sys.stderr.write(f"louis : {e.message}\n")
        return 2
    if not sys.stdin.isatty():
        piped: str = sys.stdin.read().strip()
        if piped:
            question = f"{question}\n\n{piped}"

    db: Database | None = None
    try:
        db, user = open_user(username)
        monitor: Recorder = Recorder(traces_path(), settings)
        app: App = App(settings, system_prompt, user, QuietInterface(), monitor)
        valid, data = app.structured(question, name, schema)
    except ModelException as e:
        log.error(f"[app] the model failed: {e.message}")
        sys.stderr.write(f"louis : {e.message}\n")
        return 1
    finally:
        if db is not None:
            db.close()
    if valid:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    log.info(f"===== louis stopped ({'valid' if valid else 'invalid'} reply to --ask) =====")
    return 0 if valid else 1

if __name__ == "__main__":
    args: argparse.Namespace = parse()

    if args.dashboard:
        sys.exit(report(traces_path(), open_browser=True))

    setup_logger()
    log.info(f"===== louis started in {os.getcwd()} =====")
    log.debug(f"[app] settings: {settings}")

    if args.ask is not None:
        sys.exit(ask(args.prompt, args.user, args.schema, args.ask))

    exitcode = run(args.prompt, args.user, args.plain)

    sys.exit(exitcode)
