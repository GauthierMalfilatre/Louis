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
        """ Get the session a user is most likely to want to resume: the one they were
            last active in, not simply the last one created
        """
        row = db.fetchone(
            "SELECT * FROM sessions WHERE user_id = ? ORDER BY updated_at DESC, id DESC LIMIT 1",
            (user_id,)
        )
        return cls.__from_row(db, row) if row else None

    @classmethod
    def summaries(cls, db: Database, user_id: int) -> list[dict]:
        """ Get every session of a user with its size and first message,
            most recently active first (matches what resume would reopen)
        """
        rows = db.fetchall(
            """
            SELECT s.id, s.created_at, s.updated_at,
                   (SELECT COUNT(*) FROM messages m
                    WHERE m.session_id = s.id AND m.role IN ('user', 'assistant')) AS messages,
                   (SELECT m.content FROM messages m
                    WHERE m.session_id = s.id AND m.role = 'user'
                    ORDER BY m.id LIMIT 1) AS preview
            FROM sessions s WHERE s.user_id = ? ORDER BY s.updated_at DESC, s.id DESC
            """,
            (user_id,)
        )
        return [dict(row) for row in rows]

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
            tool_name: str | None = None,
            images: list[str] | None = None
        ) -> Message:
        """ Stack a message into the session (saved immediately)

            Images stay in memory: base64 in the database would weigh down every history read,
            so a resumed session keeps its text but loses its pictures.
        """
        if not isinstance(role, str) or not isinstance(content, str):
            raise SessionException("Bad stacking")

        if self.db is None:
            # Ephemeral session: the message only lives in memory
            message: Message = Message(
                role, content, None, None, datetime.now(), tool_calls or None, tool_name,
                images or None
            )
            self.messages.append(message)
            return message

        cur = self.db.execute(
            "INSERT INTO messages (session_id, role, content, tool_name) VALUES (?, ?, ?, ?)",
            (self.id, role, content, tool_name)
        )
        row = self.db.fetchone("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,))
        # What "resume" (Session.latest) follows: the session just used, not just created
        self.db.execute(
            "UPDATE sessions SET updated_at = datetime('now', 'subsec') WHERE id = ?", (self.id,)
        )

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
            tool_name,
            images or None
        )

        # Keep the cache coherent only if it was already loaded,
        # otherwise the next access will read it from the database.
        if "messages" in self.__dict__:
            self.messages.append(message)
        return message
