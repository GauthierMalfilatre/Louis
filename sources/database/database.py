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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    -- subsec (millisecond) precision: plain datetime('now') ties within the same second,
    -- which is common for rapid tool-calling turns and would make resume fall back to id order
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'subsec'))
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, id);
-- idx_sessions_user_updated: created after the migration below, it needs the updated_at column

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    tool_name  TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS tool_calls (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    arguments  TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tool_calls_message ON tool_calls(message_id, id);
"""

# Columns added after their table: CREATE TABLE IF NOT EXISTS won't add them to an existing database
MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("messages", "tool_name", "TEXT"),
    ("sessions", "updated_at", "TEXT"),
)

class Database:
    def __init__(self, path: str | Path = "sensai.db") -> None:
        """ Open (and create if needed) the database at the given path """
        self.__conn: sqlite3.Connection = sqlite3.connect(path)
        self.__conn.row_factory = sqlite3.Row
        self.__conn.execute("PRAGMA foreign_keys = ON")
        self.__conn.executescript(SCHEMA)
        self.__migrate()

    def __migrate(self) -> None:
        """ Add the columns missing from a database created by an older version """
        for table, column, definition in MIGRATIONS:
            columns = {row["name"] for row in self.fetchall(f"PRAGMA table_info({table})")}
            if column not in columns:
                self.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        # A session with no updated_at yet was never touched by this column: its creation
        # time is the best guess for its last activity, better than leaving it unsortable
        self.execute("UPDATE sessions SET updated_at = created_at WHERE updated_at IS NULL")
        # Only safe once the column above is guaranteed to exist, fresh database or migrated
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_user_updated ON sessions(user_id, updated_at)"
        )

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
