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
from interface.web import WebInterface, HOST, PORT
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
from rag.cli import index_folder
import argparse
import json

def parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Louis")

    parser.add_argument("--prompt", type=str, default=SYSTEM_PROMPT, help="system prompt")
    parser.add_argument("--user", type=str, default=ANONYMOUS, help=f"user name, whose sessions are saved (not {ANONYMOUS}'s)")
    parser.add_argument("--plain", action="store_true", help="plain terminal output, without the curses window")
    parser.add_argument("--web", action="store_true", help="chat from a browser instead of the terminal; it also serves the public links of /share")
    parser.add_argument("--host", type=str, default=None, help=f"with --web: the address to listen on (default: {HOST}, this computer only; 0.0.0.0 opens Louis to the network, without a password)")
    parser.add_argument("--port", type=int, default=None, help=f"with --web: the port to listen on (default: {PORT})")
    parser.add_argument("--dashboard", action="store_true", help="write the metrics of the recorded calls, open them, and quit")
    parser.add_argument("--schema", type=str, help="with --ask: name or file of the JSON Schema the reply must match")
    parser.add_argument("--ask", type=str, help="with --schema: answer this question with JSON only, print it and quit "
                                                 "(text piped in is added to the question)")
    parser.add_argument("--index", type=str, default=None, metavar="FOLDER", help="index a folder of documentation or code in the knowledge base, and quit")
    parser.add_argument("--name", type=str, default=None, help="the name of the source --index makes (default: the name of the folder)")
    parser.add_argument("--exclude", action="append", default=None, metavar="PATTERN", help="with --index: leave out the files of this pattern ('config/*_grid.yml', 'tests'), kept for the next ones; --exclude '' leaves out nothing any more")
    parser.add_argument("--describe", action=argparse.BooleanOptionalAction, default=None, help="with --index: the chat model describes each passage of code, searched with it (slow the first time), kept for the next ones; --no-describe stops it")

    args: argparse.Namespace = parser.parse_args()
    if (args.schema is None) != (args.ask is None):
        parser.error("--schema and --ask go together: louis --schema <schema> --ask \"<question>\"")
    if not args.web and (args.host is not None or args.port is not None):
        parser.error("--host and --port go with --web: louis --web --port 8080")
    if args.port is not None and not 0 <= args.port <= 65535:
        parser.error("--port takes a port between 0 and 65535 (0: any free one)")
    return args

def database_path() -> str:
    """ The database of the sessions: LOUIS_DB (the launcher of install.sh), or the one of the working directory """
    return os.environ.get("LOUIS_DB") or os.path.join(os.getcwd(), settings["db.file"])

def open_user(username: str) -> tuple[Database | None, User]:
    """ The user Louis talks to, with the database its sessions are saved in (None for the anonymous one) """
    if not username or username == ANONYMOUS:
        return None, User.anonymous()
    db: Database = Database(database_path())
    log.info(f"[session] database: {db.path}")
    return db, User.get_or_create(db, username)

def serve(host: str, port: int) -> WebInterface | None:
    """
        The web interface, listening already: None if it can not (the port is taken...). The links of /share lead to
        it, unless the setting or LOUIS_SHARE_URL say where else
    """
    try:
        web: WebInterface = WebInterface(host, port, database_path())
    except OSError as e:
        log.error(f"[web] cannot listen on {host}:{port}: {e}")
        sys.stderr.write(f"louis : impossible d'écouter sur {host}:{port} : {e.strerror or e}\n")
        return None
    if not settings.get("share.base_url"):
        settings["share.base_url"] = web.url
    return web

def run(system_prompt: str, username: str, plain: bool = False, web: tuple[str, int] | None = None) -> int:
    """ Run the main programm by creating the Application and running it, in a browser with web (host, port) """

    db: Database | None = None
    try:
        # The interface is chosen here: the app only talks to it through its event bus.
        # A curses window needs a real terminal: piped or redirected, Louis writes plain text
        terminal: bool = sys.stdin.isatty() and sys.stdout.isatty()
        interface: Interface | None = serve(*web) if web is not None else CursesCLI("> ") if terminal and not plain else CLI("> ")
        if interface is None:
            return 1

        db, user = open_user(username)

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
    if args.index:
        sys.exit(index_folder(args.index, args.name, args.exclude, args.describe))

    log.info(f"===== louis started in {os.getcwd()} =====")
    log.debug(f"[app] settings: {settings}")

    if args.ask is not None:
        sys.exit(ask(args.prompt, args.user, args.schema, args.ask))

    web: tuple[str, int] | None = (args.host or HOST, PORT if args.port is None else args.port) if args.web else None
    exitcode = run(args.prompt, args.user, args.plain, web)

    sys.exit(exitcode)
