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

LOG_FILE  : str = "louis.log"
LOG_FORMAT: str = "%(asctime)s %(levelname)-5s %(message)s"

class _Formatter(logging.Formatter):
    """ Indent the lines after the first one, so a multi-line message stays inside its entry """
    def format(self, record: logging.LogRecord) -> str:
        return super().format(record).replace("\n", "\n    ")

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
    return log

def log_event(event) -> None:
    """ Log an event of the bus, subscribe it with bus.subscribe(log_event) to log every event """
    data: str = ", ".join(f"{key}={value}" for key, value in event.data.items())
    log.debug(f"[event] {event.name} {data}".rstrip())
