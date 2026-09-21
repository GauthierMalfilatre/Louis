##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## User def
##
from dataclasses import dataclass, field
from functools import cached_property
from database.database import Database
from session.session import Session

@dataclass
class User:
    db  : Database = field(repr=False, compare=False)
    name: str      = "Anonymous"
    role: str      = "user"
    id  : int | None = None

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise ValueError("User name must be a non-empty string")
        if not self.role or not isinstance(self.role, str):
            raise ValueError("User role must be a non-empty string")

    @classmethod
    def get_or_create(cls, db: Database, name: str = "Anonymous") -> "User":
        """ Get a user by name, creating it if it does not exist """
        db.execute("INSERT OR IGNORE INTO users (name) VALUES (?)", (name,))
        row = db.fetchone("SELECT * FROM users WHERE name = ?", (name,))
        return cls(db, row["name"], row["role"], row["id"])

    def save(self) -> None:
        """ Persist name / role changes """
        self.db.execute(
            "UPDATE users SET name = ?, role = ? WHERE id = ?",
            (self.name, self.role, self.id)
        )

    @cached_property
    def sessions(self) -> list[Session]:
        """ Get sessions, loaded on first access (their messages stay lazy) """
        return Session.for_user(self.db, self.id)

    def new_session(self, system_prompt: str | None = None) -> Session:
        """ Start a new session, optionally seeded with a system prompt """
        session: Session = Session.create(self.db, self.id)
        if system_prompt:
            session.stack(system_prompt, role="system")
        if "sessions" in self.__dict__:
            self.sessions.append(session)
        return session

    def last_session(self) -> Session | None:
        """ Get the most recent session without loading the whole list """
        return Session.latest(self.db, self.id)
