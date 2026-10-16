##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Store of the semantic cache: the questions answered, their meaning and their answers, in SQLite
##
## An entry belongs to a scope: the user (None: shared, or the anonymous user), the chat model, the version of the
## system prompt and the embedding model. Another model, another prompt would answer otherwise, and the vectors of
## another embedding model can not be compared. The file is only created on the first answer stored.
## An entry comes from the model, or from the seed (cache/seed/: answers written by the team, for a cache that is
## useful from the first question). The seed belongs to no user, model nor prompt, never expires, and is only replaced
## when its files change: /cache clear and the limits of the cache are for the answers of the model
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
    hits       INTEGER NOT NULL DEFAULT 0,
    -- "model" (an answer given by the model) or "seed" (written by the team, cache/seed/)
    origin     TEXT    NOT NULL DEFAULT 'model'
);
CREATE INDEX IF NOT EXISTS idx_entries_scope ON entries(model, prompt, embedder, user_id);
-- seed:<embedding model>: the version of the seed files whose questions are stored, embedded by that model
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""
MODEL: str = "model"
SEED : str = "seed"

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
    origin    : str = MODEL

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
        """
            The entries of the scope stored since then, and those of the seed, the closest in meaning to vector
            (normalized) first, with their cosine
        """
        db: sqlite3.Connection | None = self.__open(create=False)
        if db is None:
            return []
        rows = db.execute(
            "SELECT * FROM entries WHERE embedder = ? AND (origin = ? OR "
            "(model = ? AND prompt = ? AND user_id IS ? AND created_at >= ?))",
            (scope.embedder, SEED, scope.model, scope.prompt, scope.user_id, since)
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
        """ Remove an entry, of the model or of the seed (back when the seed files change): 1 if it was there """
        return self.__delete("DELETE FROM entries WHERE id = ?", (identifier,))

    def clear(self, user_id: int | None) -> int:
        """ Remove the answers of the model to a user: how many """
        return self.__delete("DELETE FROM entries WHERE origin = ? AND user_id IS ?", (MODEL, user_id))

    def drop_using(self, tools: list[str]) -> int:
        """ Remove the answers whose turn used one of these tools: how many """
        if not tools:
            return 0
        return self.__delete(
            f"DELETE FROM entries WHERE EXISTS (SELECT 1 FROM json_each(entries.tools) WHERE value IN "
            f"({', '.join('?' for _ in tools)}))", tuple(tools)
        )

    def expire(self, before: float) -> int:
        """ Remove the answers of the model stored before then: how many """
        return self.__delete("DELETE FROM entries WHERE origin = ? AND created_at < ?", (MODEL, before))

    def evict(self, most: int) -> int:
        """ Keep the most answers of the model served or stored the latest, remove the others: how many """
        return self.__delete(
            "DELETE FROM entries WHERE origin = ? AND id NOT IN (SELECT id FROM entries WHERE origin = ? "
            "ORDER BY COALESCE(last_hit, created_at) DESC, id DESC LIMIT ?)", (MODEL, MODEL, max(0, most))
        )

    def count(self, user_id: int | None) -> tuple[int, int, int]:
        """ The answers of the model to a user, the times they and the seed were served, and the questions of the seed """
        db: sqlite3.Connection | None = self.__open(create=False)
        if db is None:
            return 0, 0, 0
        row = db.execute(
            "SELECT COALESCE(SUM(origin = ? AND user_id IS ?), 0) AS entries, "
            "COALESCE(SUM(CASE WHEN origin = ? OR user_id IS ? THEN hits ELSE 0 END), 0) AS hits, "
            "COALESCE(SUM(origin = ?), 0) AS seeds FROM entries",
            (MODEL, user_id, SEED, user_id, SEED)
        ).fetchone()
        return row["entries"], row["hits"], row["seeds"]

    def seed_version(self, embedder: str) -> str | None:
        """ The version of the seed files whose questions are stored, embedded by that model: None if none is """
        db: sqlite3.Connection | None = self.__open(create=False)
        if db is None:
            return None
        row = db.execute("SELECT value FROM meta WHERE key = ?", (f"seed:{embedder}",)).fetchone()
        return row["value"] if row else None

    def replace_seed(self, embedder: str, version: str, entries: list[tuple[str, str, np.ndarray]], now: float) -> int:
        """
            Put the questions of the seed files in place of those stored before, embedded by that model: (question, answer,
            vector normalized) each. All of them or none: two louis starting at once never store it twice. How many
        """
        db: sqlite3.Connection = self.__open()
        with db:
            db.execute("DELETE FROM entries WHERE origin = ? AND embedder = ?", (SEED, embedder))
            db.executemany(
                "INSERT INTO entries (user_id, model, prompt, embedder, question, answer, vector, tools, guard, created_at, "
                "origin) VALUES (NULL, '', '', ?, ?, ?, ?, '[]', 1, ?, ?)",
                [(embedder, question, answer, vector.astype(np.float32).tobytes(), now, SEED)
                 for question, answer, vector in entries]
            )
            db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (f"seed:{embedder}", version))
        return len(entries)

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
                     row["created_at"], row["hits"], row["origin"])

    def __open(self, create: bool = True) -> sqlite3.Connection | None:
        """ The connection, opened on first use. Without create, None while there is no file: nothing is stored yet """
        if self.__conn is None:
            if not create and not os.path.exists(self.__path):
                return None
            self.__conn = sqlite3.connect(self.__path)
            self.__conn.row_factory = sqlite3.Row
            self.__conn.executescript(SCHEMA)
            # A cache made before the seed: its entries are all answers of the model
            if "origin" not in {row["name"] for row in self.__conn.execute("PRAGMA table_info(entries)")}:
                with self.__conn:
                    self.__conn.execute(f"ALTER TABLE entries ADD COLUMN origin TEXT NOT NULL DEFAULT '{MODEL}'")
        return self.__conn
