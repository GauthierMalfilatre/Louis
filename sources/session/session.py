##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Session file
##
from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property
import json
import sqlite3
from .message import Message
from database.database import Database
from tool.tools import ToolCall

class SessionException(Exception):
    def __init__(self, message: str = "Bad Session usage") -> None:
        self.message = message
        super().__init__(self.message)

@dataclass
class Session:
    db        : Database | None = field(repr=False, compare=False)
    user_id   : int | None
    id        : int | None      = None
    created_at: datetime | None = None

    @classmethod
    def __from_row(cls, db: Database, row: sqlite3.Row) -> "Session":
        return cls(
            db,
            row["user_id"],
            row["id"],
            datetime.fromisoformat(row["created_at"])
        )

    @classmethod
    def ephemeral(cls) -> "Session":
        """ Create a memory-only session, never written to the database """
        return cls(None, None, None, datetime.now())

    @classmethod
    def create(cls, db: Database, user_id: int) -> "Session":
        """ Create a new empty session for a user """
        cur = db.execute("INSERT INTO sessions (user_id) VALUES (?)", (user_id,))
        row = db.fetchone("SELECT * FROM sessions WHERE id = ?", (cur.lastrowid,))
        return cls.__from_row(db, row)

    @classmethod
    def for_user(cls, db: Database, user_id: int) -> list["Session"]:
        """ Get every session of a user, oldest first (messages are NOT loaded) """
        rows = db.fetchall(
            "SELECT * FROM sessions WHERE user_id = ? ORDER BY id", (user_id,)
        )
        return [cls.__from_row(db, row) for row in rows]

    @classmethod
    def latest(cls, db: Database, user_id: int) -> "Session | None":
        """ Get the most recent session of a user, if any """
        row = db.fetchone(
            "SELECT * FROM sessions WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,)
        )
        return cls.__from_row(db, row) if row else None

    def __load_tool_calls(self, message_id: int) -> list[ToolCall] | None:
        """ Get the tool calls attached to a message, if any """
        rows = self.db.fetchall(
            "SELECT * FROM tool_calls WHERE message_id = ? ORDER BY id", (message_id,)
        )
        if not rows:
            return None
        return [ToolCall(row["name"], json.loads(row["arguments"])) for row in rows]

    @cached_property
    def messages(self) -> list[Message]:
        """ Get messages, loaded from the database on first access """
        if self.db is None:
            return []
        rows = self.db.fetchall(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id", (self.id,)
        )
        return [
            Message(
                row["role"],
                row["content"],
                row["id"],
                row["session_id"],
                datetime.fromisoformat(row["created_at"]),
                self.__load_tool_calls(row["id"]),
                row["tool_name"]
            )
            for row in rows
        ]

    @property
    def history(self) -> list[dict]:
        """ Get history in the model API format """
        return [message.to_dict() for message in self.messages]

    def stack(
            self,
            content: str,
            *,
            role: str = "user",
            tool_calls: list[ToolCall] | None = None,
            tool_name: str | None = None
        ) -> Message:
        """ Stack a message into the session (saved immediately) """
        if not isinstance(role, str) or not isinstance(content, str):
            raise SessionException("Bad stacking")

        if self.db is None:
            # Ephemeral session: the message only lives in memory
            message: Message = Message(
                role, content, None, None, datetime.now(), tool_calls or None, tool_name
            )
            self.messages.append(message)
            return message

        cur = self.db.execute(
            "INSERT INTO messages (session_id, role, content, tool_name) VALUES (?, ?, ?, ?)",
            (self.id, role, content, tool_name)
        )
        row = self.db.fetchone("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,))

        for call in tool_calls or []:
            self.db.execute(
                "INSERT INTO tool_calls (message_id, name, arguments) VALUES (?, ?, ?)",
                (row["id"], call.name, json.dumps(call.arguments))
            )

        message: Message = Message(
            role,
            content,
            row["id"],
            self.id,
            datetime.fromisoformat(row["created_at"]),
            tool_calls or None,
            tool_name
        )

        # Keep the cache coherent only if it was already loaded,
        # otherwise the next access will read it from the database.
        if "messages" in self.__dict__:
            self.messages.append(message)
        return message
