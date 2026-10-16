##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Store of the semantic cache: the questions answered, their meaning and their answers, in SQLite
##
## An entry belongs to a scope: the user (None: shared, or the anonymous user), the chat model, the version of the
## system prompt and the embedding model. Another model, another prompt would answer otherwise, and the vectors of
## another embedding model can not be compared. The file is only created on the first answer stored
##
from dataclasses import dataclass
import json
import numpy as np
import os
import sqlite3

SCHEMA: str = """
CREATE TABLE IF NOT EXISTS entries (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER,
    model      TEXT    NOT NULL,
    prompt     TEXT    NOT NULL,
    embedder   TEXT    NOT NULL,
    question   TEXT    NOT NULL,
    answer     TEXT    NOT NULL,
    vector     BLOB    NOT NULL,
    -- the tools the answer used, as a JSON list: the knowledge base changed, the answers that read it are forgotten
    tools      TEXT    NOT NULL DEFAULT '[]',
    -- stored while the guard was on: the answer went through its output rails
    guard      INTEGER NOT NULL DEFAULT 0,
    created_at REAL    NOT NULL,
    last_hit   REAL,
    hits       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_entries_scope ON entries(model, prompt, embedder, user_id);
"""

@dataclass(frozen=True, slots=True)
class Scope:
    """ Whose answers, by which models, on which prompt (its version) """
    user_id : int | None
    model   : str
    prompt  : str
    embedder: str

@dataclass(frozen=True, slots=True)
class Entry:
    """ A question answered before """
    id        : int
    question  : str
    answer    : str
    tools     : list[str]
    guard     : bool
    created_at: float
    hits      : int

def normalized(vector: list[float] | np.ndarray) -> np.ndarray | None:
    """ A vector of length 1, for its dot product with another to be their cosine. None for a null one """
    array: np.ndarray = np.asarray(vector, dtype=np.float32)
    norm: float = float(np.linalg.norm(array))
    return array / norm if norm else None

class Store:
    """ The entries of the cache, in a SQLite file opened on first use """
    def __init__(self, path: str):
        """ Init a store on path, created when the first entry is stored """
        self.__path: str                       = path
        self.__conn: sqlite3.Connection | None = None

    @property
    def path(self) -> str:
        """ Get the file of the cache """
        return self.__path

    def close(self) -> None:
        """ Close the file, opened again when needed """
        if self.__conn is not None:
            self.__conn.close()
            self.__conn = None

    def nearest(self, scope: Scope, vector: np.ndarray, since: float, most: int = 5) -> list[tuple[Entry, float]]:
        """ The entries of the scope stored since then, the closest in meaning to vector (normalized) first, with their cosine """
        db: sqlite3.Connection | None = self.__open(create=False)
        if db is None:
            return []
        rows = db.execute(
            "SELECT * FROM entries WHERE model = ? AND prompt = ? AND embedder = ? AND user_id IS ? AND created_at >= ?",
            (scope.model, scope.prompt, scope.embedder, scope.user_id, since)
        ).fetchall()
        rows = [row for row in rows if len(row["vector"]) == vector.nbytes]
        if not rows:
            return []
        scores: np.ndarray = np.vstack([np.frombuffer(row["vector"], dtype=np.float32) for row in rows]) @ vector
        order: np.ndarray = np.argsort(-scores)[:most]
        return [(self.__entry(rows[i]), float(scores[i])) for i in order]

    def add(self, scope: Scope, question: str, answer: str, vector: np.ndarray, tools: list[str], guard: bool,
            now: float) -> int:
        """ Store an answer, its vector normalized: its id """
        db: sqlite3.Connection = self.__open()
        with db:
            return db.execute(
                "INSERT INTO entries (user_id, model, prompt, embedder, question, answer, vector, tools, guard, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (scope.user_id, scope.model, scope.prompt, scope.embedder, question, answer,
                 vector.astype(np.float32).tobytes(), json.dumps(sorted(set(tools))), int(guard), now)
            ).lastrowid

    def hit(self, identifier: int, now: float) -> None:
        """ An entry was served once more """
        db: sqlite3.Connection = self.__open()
        with db:
            db.execute("UPDATE entries SET hits = hits + 1, last_hit = ? WHERE id = ?", (now, identifier))

    def remove(self, identifier: int) -> int:
        """ Remove an entry: 1 if it was there """
        return self.__delete("DELETE FROM entries WHERE id = ?", (identifier,))

    def clear(self, user_id: int | None) -> int:
        """ Remove the entries of a user: how many """
        return self.__delete("DELETE FROM entries WHERE user_id IS ?", (user_id,))

    def drop_using(self, tools: list[str]) -> int:
        """ Remove the entries whose answer used one of these tools: how many """
        if not tools:
            return 0
        return self.__delete(
            f"DELETE FROM entries WHERE EXISTS (SELECT 1 FROM json_each(entries.tools) WHERE value IN "
            f"({', '.join('?' for _ in tools)}))", tuple(tools)
        )

    def expire(self, before: float) -> int:
        """ Remove the entries stored before then: how many """
        return self.__delete("DELETE FROM entries WHERE created_at < ?", (before,))

    def evict(self, most: int) -> int:
        """ Keep the most entries served or stored the latest, remove the others: how many """
        return self.__delete(
            "DELETE FROM entries WHERE id NOT IN "
            "(SELECT id FROM entries ORDER BY COALESCE(last_hit, created_at) DESC, id DESC LIMIT ?)", (max(0, most),)
        )

    def count(self, user_id: int | None) -> tuple[int, int]:
        """ The entries of a user, and how many times they were served """
        db: sqlite3.Connection | None = self.__open(create=False)
        if db is None:
            return 0, 0
        row = db.execute("SELECT COUNT(*) AS entries, COALESCE(SUM(hits), 0) AS hits FROM entries WHERE user_id IS ?",
                         (user_id,)).fetchone()
        return row["entries"], row["hits"]

    def __delete(self, query: str, parameters: tuple) -> int:
        """ Run a DELETE: the rows removed, 0 when there is no file yet """
        db: sqlite3.Connection | None = self.__open(create=False)
        if db is None:
            return 0
        with db:
            return db.execute(query, parameters).rowcount

    @staticmethod
    def __entry(row: sqlite3.Row) -> Entry:
        return Entry(row["id"], row["question"], row["answer"], json.loads(row["tools"] or "[]"), bool(row["guard"]),
                     row["created_at"], row["hits"])

    def __open(self, create: bool = True) -> sqlite3.Connection | None:
        """ The connection, opened on first use. Without create, None while there is no file: nothing is stored yet """
        if self.__conn is None:
            if not create and not os.path.exists(self.__path):
                return None
            self.__conn = sqlite3.connect(self.__path)
            self.__conn.row_factory = sqlite3.Row
            self.__conn.executescript(SCHEMA)
        return self.__conn
