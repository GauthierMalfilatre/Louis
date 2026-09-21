##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## SQLite database wrapper
##
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA: str = """
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    role       TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, id);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
"""

class Database:
    def __init__(self, path: str | Path = "sensai.db") -> None:
        """ Open (and create if needed) the database at the given path """
        self.__conn: sqlite3.Connection = sqlite3.connect(path)
        self.__conn.row_factory = sqlite3.Row
        self.__conn.execute("PRAGMA foreign_keys = ON")
        self.__conn.executescript(SCHEMA)

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """ Run a write statement in its own transaction """
        with self.__conn:
            return self.__conn.execute(sql, params)

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        """ Run a query and get the first row """
        return self.__conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        """ Run a query and get every row """
        return self.__conn.execute(sql, params).fetchall()

    def close(self) -> None:
        """ Close the connection """
        self.__conn.close()
