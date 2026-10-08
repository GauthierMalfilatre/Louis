##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Logger: what louis does, step by step, written to louis.log in the working directory
##
## Usage:  from logger.logger import log
##         log.info("something happened")
##         log.debug("some detail")
##
import logging
import os
import sys
from collections.abc import Callable

LOG_FILE  : str = "louis.log"
LOG_FORMAT: str = "%(asctime)s %(levelname)-5s %(message)s"

# What every line goes through before it is written, set by protect(): the line as it is by default
_scrub: Callable[[str], str] = lambda line: line

class _Formatter(logging.Formatter):
    """ Indent the lines after the first one, so a multi-line message stays inside its entry """
    def format(self, record: logging.LogRecord) -> str:
        # Scrubbed whole, traceback included: no call of log.* can write around it
        return _scrub(super().format(record)).replace("\n", "\n    ")

log: logging.Logger = logging.getLogger("louis")
# Nothing is written before setup_logger(): importing a module (in a test...) never creates the file
log.addHandler(logging.NullHandler())
log.propagate = False

def setup_logger(directory: str | None = None, level: int = logging.DEBUG) -> logging.Logger:
    """ Write the log to louis.log, in the given directory or the working one """
    path: str = os.path.join(directory or os.getcwd(), LOG_FILE)
    try:
        handler: logging.Handler = logging.FileHandler(path, encoding="utf-8")
    except OSError as e:
        # A read-only directory must not stop louis: it runs without its log
        sys.stderr.write(f"Cannot write the log to {path}: {e.strerror}\n")
        return log
    handler.setFormatter(_Formatter(LOG_FORMAT))
    log.addHandler(handler)
    log.setLevel(level)
    # The warnings of the libraries (requests, ddgs...) go to the log too: printed on stderr, they would
    # land in the middle of the curses window
    logging.getLogger().addHandler(handler)
    logging.captureWarnings(True)
    return log

def protect(scrub: Callable[[str], str]) -> None:
    """ Write every line of the log through scrub, from now on: the guard hides there what it hides elsewhere """
    global _scrub
    _scrub = scrub

def scrub(text: str) -> str:
    """ A text as the log may keep it: for what is written elsewhere than the log (the traces of the monitoring) """
    return _scrub(text)

def log_event(event) -> None:
    """
        Log an event of the bus, subscribe it with bus.subscribe(log_event) to log every event. A whole conversation
        (the history of SESSION_RESUMED) is logged as its size: it is in the database already
    """
    data: str = ", ".join(
        f"{key}={f'[{len(value)} messages]' if key == 'history' and isinstance(value, list) else value}"
        for key, value in event.data.items()
    )
    log.debug(f"[event] {event.name} {data}".rstrip())
