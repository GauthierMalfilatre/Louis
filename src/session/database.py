##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## SQLite database where the users, their sessions and their messages are saved
##
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
import sqlite3

SCHEMA: str = """
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    cwd        TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, id);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    tool_calls TEXT,
    tool_name  TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
"""

def now() -> str:
    """ The current time, in UTC, as it is saved in the database """
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

class Database:
    """ A connection to the database, which creates its tables if they do not exist """
    def __init__(self, path: str):
        """ Open the database, creating the file if needed """
        self.__path: str = path
        self.__grouped: bool = False
        self.__conn: sqlite3.Connection = sqlite3.connect(path)
        self.__conn.row_factory = sqlite3.Row
        self.__conn.execute("PRAGMA foreign_keys = ON")
        self.__conn.executescript(SCHEMA)
        # A conversation without a message of the user is never saved: remove the ones older versions left
        self.execute("DELETE FROM sessions WHERE id NOT IN (SELECT session_id FROM messages WHERE role = 'user')")

    @property
    def path(self) -> str:
        """ Get the path of the database file """
        return self.__path

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """ Run a write, committed at once (or with its transaction): a crash never loses what was said before it """
        if self.__grouped:
            return self.__conn.execute(sql, params)
        with self.__conn:
            return self.__conn.execute(sql, params)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """ Group the writes made inside: all of them are saved, or none """
        if self.__grouped:
            yield
            return
        self.__grouped = True
        try:
            with self.__conn:
                yield
        finally:
            self.__grouped = False

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        """ Run a query, and get its first row """
        return self.__conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        """ Run a query, and get all its rows """
        return self.__conn.execute(sql, params).fetchall()

    def close(self) -> None:
        """ Close the connection """
        self.__conn.close()
