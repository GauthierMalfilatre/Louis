##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Session class
##
from dataclasses import dataclass, field
from functools import cached_property
from tool.tool_call import ToolCall
from .database import Database, now
from .message import Message
from logger.logger import log
import sqlite3

@dataclass
class Session:
    """ A conversation with Louis, saved message by message, unless it has no database (anonymous user) """
    cwd       : str
    user_id   : int | None      = None
    id        : int | None      = None
    created_at: str | None      = None
    db        : Database | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_row(cls, db: Database, row: sqlite3.Row) -> "Session":
        """ Rebuild a session saved in the database, without its messages """
        return cls(row["cwd"], row["user_id"], row["id"], row["created_at"], db)

    @classmethod
    def create(cls, db: Database | None, user_id: int | None, cwd: str) -> "Session":
        """
            Start a session in the working directory cwd. With a db, it is saved on the first message of the
            user: until then its id is None, and a conversation where the user said nothing is never kept
        """
        session: Session = cls(cwd, user_id, None, now(), db)
        # A brand new session has nothing to load
        session.__dict__["messages"] = []
        return session

    @property
    def saved(self) -> bool:
        """ Whether the session is in the database """
        return self.id is not None

    @cached_property
    def messages(self) -> list[Message]:
        """ Get the messages, read from the database on first access only """
        if self.db is None:
            return []
        rows = self.db.fetchall("SELECT * FROM messages WHERE session_id = ? ORDER BY id", (self.id,))
        return [Message.from_row(row) for row in rows]

    def first_user_message(self) -> str | None:
        """ Get the first message of the user, without loading the whole session """
        if self.db is None or "messages" in self.__dict__:
            return next((message.content for message in self.messages if message.role == "user"), None)
        row = self.db.fetchone(
            "SELECT content FROM messages WHERE session_id = ? AND role = 'user' ORDER BY id LIMIT 1", (self.id,)
        )
        return row["content"] if row else None

    @property
    def history(self) -> list[dict]:
        """ Get the messages in the format of the model API """
        return [message.to_dict() for message in self.messages]

    def add(
            self,
            role: str,
            content: str,
            *,
            tool_calls: list[ToolCall] | None = None,
            tool_name: str | None = None
        ) -> Message:
        """ Add a message at the end of the session, saved at once from the first message of the user on """
        message: Message = Message(
            role, content if isinstance(content, str) else str(content or ""), tool_calls or None, tool_name,
            created_at=now()
        )
        if self.db is not None and self.saved:
            self.__insert(message)
        elif self.db is not None and role == "user":
            # The user says something: the session is worth keeping, with what it held until now
            try:
                with self.db.transaction():
                    self.id = self.db.execute(
                        "INSERT INTO sessions (user_id, cwd, created_at) VALUES (?, ?, ?)",
                        (self.user_id, self.cwd, self.created_at)
                    ).lastrowid
                    for earlier in self.messages:
                        self.__insert(earlier)
                    self.__insert(message)
            except Exception:
                # Rolled back: the session is still not saved
                self.id = None
                raise
            log.info(f"[session] #{self.id} saved, on the first message of the user")
        # Not loaded yet: the first access reads it from the database, with the others
        if "messages" in self.__dict__:
            self.messages.append(message)
        return message

    def __insert(self, message: Message) -> None:
        """ Write a message of the session in the database """
        message.id = self.db.execute(
            "INSERT INTO messages (session_id, role, content, tool_calls, tool_name, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (self.id, message.role, message.content, message.calls_json(), message.tool_name, message.created_at)
        ).lastrowid
