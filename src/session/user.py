##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## User class
##
from dataclasses import dataclass, field
from functools import cached_property
from .database import Database, now
from .session import Session

ANONYMOUS: str = "Anonymous"

@dataclass
class User:
    """ Who talks to Louis: a named user is saved with its sessions, the anonymous one never is """
    name           : str             = ANONYMOUS
    id             : int | None      = None
    created_at     : str | None      = None
    db             : Database | None = field(default=None, repr=False, compare=False)
    current_session: Session | None  = field(default=None, repr=False, compare=False)

    @classmethod
    def anonymous(cls) -> "User":
        """ Get the anonymous user, whose sessions only live in memory """
        user: User = cls(ANONYMOUS, created_at=now())
        # Nothing in the database: its sessions are the ones started now
        user.__dict__["sessions"] = []
        return user

    @classmethod
    def get_or_create(cls, db: Database, name: str) -> "User":
        """ Get a user from the database by its name, created if it does not exist """
        if not name or name == ANONYMOUS:
            raise ValueError(f"A saved user needs a name, other than '{ANONYMOUS}'")
        db.execute("INSERT OR IGNORE INTO users (name, created_at) VALUES (?, ?)", (name, now()))
        row = db.fetchone("SELECT * FROM users WHERE name = ?", (name,))
        return cls(row["name"], row["id"], row["created_at"], db)

    @property
    def is_anonymous(self) -> bool:
        """ Whether the user is never saved """
        return self.db is None

    @cached_property
    def sessions(self) -> list[Session]:
        """ Get the sessions, oldest first, read from the database on first access only (not their messages) """
        rows = self.db.fetchall("SELECT * FROM sessions WHERE user_id = ? ORDER BY id", (self.id,))
        return [Session.from_row(self.db, row) for row in rows]

    def new_session(self, cwd: str) -> Session:
        """ Start a new session in the working directory cwd, which becomes the current one """
        self.current_session = Session.create(self.db, self.id, cwd)
        # Not loaded yet: the first access reads it from the database, with the others
        if "sessions" in self.__dict__:
            self.sessions.append(self.current_session)
        return self.current_session

    def get_session(self, session_id: int) -> Session | None:
        """ Get one of the sessions of the user by its id, None if it has no such session """
        return next((session for session in self.sessions if session.id == session_id), None)
