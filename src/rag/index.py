##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Index: the passages of the sources the user indexed, searched by keywords (SQLite FTS5) and by meaning (vectors)
##
## One SQLite file, as the sessions have theirs. A source is a folder indexed under a name, its files are
## cut into passages (chunks), and each passage has its vector when the embedding model answered.
## A search runs both ways and merges them (reciprocal rank fusion): the keywords find the exact name of a function,
## the vectors find what a question means without using its words.
## A filter (Filter) keeps the passages of some files only, by their source, their path or their kind: both searches
## are made inside it, so the pool they give is all of its files, not what is left of the best ones after it
##
from dataclasses import dataclass, field
from rag.chunker import Chunk
from session.database import now
import fnmatch
import json
import numpy as np
import os
import re
import sqlite3

SCHEMA: str = """
CREATE TABLE IF NOT EXISTS sources (
    name       TEXT PRIMARY KEY,
    root       TEXT NOT NULL,
    model      TEXT,
    updated_at TEXT NOT NULL,
    exclude    TEXT,
    chunker    INTEGER,
    describe   INTEGER
);

CREATE TABLE IF NOT EXISTS files (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    source   TEXT NOT NULL REFERENCES sources(name) ON DELETE CASCADE,
    path     TEXT NOT NULL,
    hash     TEXT NOT NULL,
    embedded INTEGER NOT NULL DEFAULT 0,
    UNIQUE (source, path)
);

CREATE TABLE IF NOT EXISTS chunks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    start_line INTEGER NOT NULL,
    end_line   INTEGER NOT NULL,
    text       TEXT NOT NULL,
    vector     BLOB,
    context    TEXT,
    description TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_id);

-- rowid is the id of the chunk. Porter stems the words: "parsing" finds "parse"
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, path, tokenize = 'porter unicode61');

-- What the chat model wrote of a passage, by what it was given (key: a hash of the model, the path and the passage):
-- a source indexed again, or cut again, does not ask again for the passages that did not change
CREATE TABLE IF NOT EXISTS descriptions (
    key        TEXT PRIMARY KEY,
    source     TEXT NOT NULL,
    text       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_descriptions_source ON descriptions(source);
"""

# The columns added since the first index files: added to an older file when it is opened, its rows kept
# (sources.exclude: the patterns left out of a folder, JSON; sources.chunker: the version of the cutting its passages
# were made with; sources.describe: whether the chat model describes its passages of code; chunks.context: where a
# passage is in its file, "class Agent › def run"; chunks.description: what it does, written by the chat model)
COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("sources", "exclude", "TEXT"), ("sources", "chunker", "INTEGER"), ("sources", "describe", "INTEGER"),
    ("chunks", "context", "TEXT"), ("chunks", "description", "TEXT")
)

# The rank of a passage counts for 1 / (RRF + rank) in each list it is in: the usual constant of the fusion
RRF: int = 60
# Passages taken from each list, per passage asked for, before they are merged
POOL: int = 5
# Words of a question searched by keywords at most, and those too common to tell a passage from another
QUERY_WORDS: int = 16
STOPWORDS: frozenset[str] = frozenset(
    "a an the of to in on at for and or is are be do does how what why which with from by as it this that i you "
    "le la les un une des de du et ou en dans sur pour par avec est sont que qui quoi comment pourquoi ce cette".split()
)

# What a file is, told by its extension: a question on the code is not answered by a file of settings or a report
KINDS: dict[str, frozenset[str]] = {
    "code": frozenset(
        ".py .pyi .ipynb .c .h .cpp .hpp .cc .cxx .cs .java .kt .scala .go .rs .js .jsx .ts .tsx .mjs .vue .svelte .rb "
        ".php .swift .m .lua .pl .sh .bash .zsh .ps1 .sql .r .jl .hs .ml .ex .exs .erl .clj .dart .zig .asm .s".split()
    ),
    "doc": frozenset(".md .markdown .rst .txt .adoc .org .tex .html .htm .man".split()),
    "config": frozenset(".yml .yaml .toml .ini .cfg .conf .json .jsonc .xml .properties .lock .gradle .cmake".split()),
}
# Build files, by their name: code
CODE_NAMES: frozenset[str] = frozenset({"makefile", "dockerfile", "cmakelists.txt", "rakefile", "gemfile", "justfile"})
# Anything else (a .csv, a log...) is data
DATA: str = "data"

def kind_of(path: str) -> str:
    """ What a file is: "code", "doc", "config" or "data" """
    name: str = os.path.basename(path).lower()
    if name in CODE_NAMES:
        return "code"
    extension: str = os.path.splitext(name)[1]
    return next((kind for kind, extensions in KINDS.items() if extension in extensions), DATA)

def path_matches(path: str, pattern: str) -> bool:
    """
        Whether a path of a source is in a pattern (of the model, or of the user's excludes): a glob from the root
        ("src/auth/*", "*.py"), anywhere below it ("auth/*"), or without a wildcard a part of the path ("src/auth",
        "auth"). The case does not matter: the model writes "userservice" for "UserService"
    """
    relative: str = path.lstrip("/").lower()
    pattern = pattern.strip().lstrip("/").lower()
    if not pattern:
        return True
    if not any(char in pattern for char in "*?["):
        return pattern.rstrip("/") in relative
    return fnmatch.fnmatchcase(relative, pattern) or fnmatch.fnmatchcase(relative, "*/" + pattern)

@dataclass(frozen=True, slots=True)
class Filter:
    """ Which passages a search may give: those of a source (None: all), of a path (see path_matches), of some kinds """
    source: str | None      = None
    path  : str | None      = None
    kinds : frozenset[str]  = field(default_factory=frozenset)

    @property
    def on_files(self) -> bool:
        """ Check if it keeps some files of the sources only, not whole sources """
        return bool(self.path or self.kinds)

    def keeps(self, path: str) -> bool:
        """ Whether a file of the source is kept """
        return (not self.kinds or kind_of(path) in self.kinds) and (not self.path or path_matches(path, self.path))

@dataclass(frozen=True, slots=True)
class Hit:
    """
        A passage found: where it is (the source, the path from its root, the lines) and its text. score is what it
        is ranked by: the fusion of the search, or the reranker's once it read it (the fusion is then kept in fused)
    """
    source: str
    path  : str
    start : int
    end   : int
    text  : str
    score : float
    fused  : float | None = None
    # Where it is in its file ("class Trainer › def run(self)"), "" when nothing is known of it (rag/context.py)
    context: str = ""
    # What it does, written by the chat model at indexing, "" when its source is not described (rag/describer.py)
    description: str = ""

def pack(vector: list[float]) -> bytes:
    """ A vector as it is saved: unit length (a dot product is then a cosine), 32 bits per number """
    array: np.ndarray = np.asarray(vector, dtype=np.float32)
    norm: float = float(np.linalg.norm(array))
    return (array / norm if norm else array).tobytes()

class Index:
    """ An index in a SQLite file, created when something is first written to it: searching never creates one """
    def __init__(self, path: str):
        """ Open the index if its file exists """
        self.__path  : str                           = path
        self.__conn  : sqlite3.Connection | None     = None
        # The vectors of the sources of one embedding model, loaded on the first search and dropped by any change
        self.__matrix: tuple[str, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None = None
        if os.path.exists(path):
            self.__open()

    @property
    def path(self) -> str:
        """ Get the path of the index file """
        return self.__path

    @property
    def empty(self) -> bool:
        """ Check if nothing is indexed """
        return self.__conn is None or self.__conn.execute("SELECT 1 FROM chunks LIMIT 1").fetchone() is None

    def close(self) -> None:
        """ Close the file """
        if self.__conn is not None:
            self.__conn.close()
            self.__conn = None

    def sources(self) -> list[dict]:
        """ The sources, with how many files, passages and vectors each has """
        if self.__conn is None:
            return []
        rows = self.__conn.execute(
            "SELECT s.name, s.root, s.model, s.updated_at, s.exclude, COALESCE(s.describe, 0) AS describe,"
            " (SELECT COUNT(*) FROM files f WHERE f.source = s.name) AS files,"
            " (SELECT COUNT(*) FROM chunks c JOIN files f ON f.id = c.file_id WHERE f.source = s.name) AS chunks,"
            " (SELECT COUNT(*) FROM chunks c JOIN files f ON f.id = c.file_id"
            "   WHERE f.source = s.name AND c.vector IS NOT NULL) AS embedded"
            " FROM sources s ORDER BY s.name"
        ).fetchall()
        return [{**dict(row), "exclude": json.loads(row["exclude"] or "[]"), "describe": bool(row["describe"])}
                for row in rows]

    def files(self, source: str) -> dict[str, tuple[str, bool]]:
        """ The files of a source: for each path, the hash of what was indexed and whether it has its vectors """
        if self.__conn is None:
            return {}
        rows = self.__conn.execute("SELECT path, hash, embedded FROM files WHERE source = ?", (source,)).fetchall()
        return {row["path"]: (row["hash"], bool(row["embedded"])) for row in rows}

    def begin(self, source: str, root: str, model: str | None, chunker: int = 0,
              exclude: list[str] | None = None, describe: bool | None = None) -> tuple[list[str], bool]:
        """
            Start (or go on with) a source, and give what it keeps from one indexing to the next: the patterns of paths
            left out of it (exclude when given, they replace those it had) and whether its code is described (describe
            when given). Its vectors belong to one embedding model: with another one, the old vectors are of no use,
            and its files are embedded again. Without a model (none answers), they stay. Its passages were cut by one
            version of the chunker, and described or not: when either changes, all its files are read again
        """
        db: sqlite3.Connection = self.__open()
        row = db.execute("SELECT model, exclude, chunker, describe FROM sources WHERE name = ?", (source,)).fetchone()
        patterns: list[str] = ([pattern for pattern in exclude if pattern.strip()] if exclude is not None
                               else json.loads(row["exclude"] or "[]") if row is not None else [])
        described: bool = describe if describe is not None else bool(row["describe"]) if row is not None else False
        with db:
            if row is None:
                db.execute("INSERT INTO sources(name, root, model, updated_at, exclude, chunker, describe)"
                           " VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (source, root, model, now(), json.dumps(patterns), chunker, int(described)))
            else:
                if model and row["model"] and row["model"] != model:
                    db.execute("UPDATE chunks SET vector = NULL WHERE file_id IN (SELECT id FROM files WHERE source = ?)",
                               (source,))
                    db.execute("UPDATE files SET embedded = 0 WHERE source = ?", (source,))
                if (row["chunker"] or 0) != chunker or bool(row["describe"]) != described:
                    # No hash matches any more: every file is cut again, and embedded again (its descriptions, if any,
                    # come from the cache when its passages did not change)
                    db.execute("UPDATE files SET hash = '' WHERE source = ?", (source,))
                db.execute("UPDATE sources SET root = ?, model = COALESCE(?, model), updated_at = ?, exclude = ?,"
                           " chunker = ?, describe = ? WHERE name = ?",
                           (root, model, now(), json.dumps(patterns), chunker, int(described), source))
        self.__matrix = None
        return patterns, described

    def described(self, key: str) -> str | None:
        """ What the chat model wrote of a passage before, None if it never did """
        if self.__conn is None:
            return None
        row = self.__conn.execute("SELECT text FROM descriptions WHERE key = ?", (key,)).fetchone()
        return row["text"] if row is not None else None

    def remember(self, source: str, key: str, text: str) -> None:
        """ Keep what the chat model wrote of a passage: saved at once, a Ctrl+C does not lose it """
        db: sqlite3.Connection = self.__open()
        with db:
            db.execute("INSERT OR REPLACE INTO descriptions(key, source, text) VALUES (?, ?, ?)", (key, source, text))

    def put(self, source: str, path: str, digest: str, chunks: list[Chunk], vectors: list[list[float]] | None,
            contexts: list[str] | None = None, descriptions: list[str] | None = None) -> None:
        """
            Save a file of a source, in place of what was indexed of it: all its passages, or none. The context and the
            description of a passage are searched by keywords with its text: "run" finds the middle of a function that
            never says it, "clavier" the code that only says K_LEFT
        """
        db: sqlite3.Connection = self.__open()
        with db:
            self.__delete(db, source, path)
            file_id: int = db.execute(
                "INSERT INTO files(source, path, hash, embedded) VALUES (?, ?, ?, ?)",
                (source, path, digest, int(vectors is not None))
            ).lastrowid
            for i, chunk in enumerate(chunks):
                context: str = contexts[i] if contexts else ""
                description: str = descriptions[i] if descriptions else ""
                chunk_id: int = db.execute(
                    "INSERT INTO chunks(file_id, start_line, end_line, text, vector, context, description)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (file_id, chunk.start, chunk.end, chunk.text, pack(vectors[i]) if vectors else None, context or None,
                     description or None)
                ).lastrowid
                searched: str = "\n".join(part for part in (context, description, chunk.text) if part)
                db.execute("INSERT INTO chunks_fts(rowid, text, path) VALUES (?, ?, ?)", (chunk_id, searched, path))
        self.__matrix = None

    def drop(self, source: str, path: str) -> None:
        """ Forget a file of a source, gone from its folder """
        db: sqlite3.Connection = self.__open()
        with db:
            self.__delete(db, source, path)
        self.__matrix = None

    def forget(self, source: str) -> int:
        """ Forget a whole source: the number of passages removed, 0 if there is no such source """
        if self.__conn is None:
            return 0
        db: sqlite3.Connection = self.__conn
        count: int = db.execute(
            "SELECT COUNT(*) FROM chunks c JOIN files f ON f.id = c.file_id WHERE f.source = ?", (source,)
        ).fetchone()[0]
        with db:
            db.execute("DELETE FROM chunks_fts WHERE rowid IN"
                       " (SELECT c.id FROM chunks c JOIN files f ON f.id = c.file_id WHERE f.source = ?)", (source,))
            db.execute("DELETE FROM descriptions WHERE source = ?", (source,))
            db.execute("DELETE FROM sources WHERE name = ?", (source,))
        self.__matrix = None
        return count

    def matching(self, where: Filter) -> list[int]:
        """ The ids of the files a filter keeps """
        if self.__conn is None:
            return []
        rows = self.__conn.execute(
            "SELECT id, path FROM files" + (" WHERE source = ?" if where.source else ""),
            (where.source,) if where.source else ()
        ).fetchall()
        return [row["id"] for row in rows if where.keeps(row["path"])]

    def outline(self, source: str, depth: int = 2) -> dict:
        """
            What a source holds, to tell the model: its folders (depth levels from its root at most, "." for the files
            at its root) with their passages, the most first, and how many files of each kind
        """
        if self.__conn is None:
            return {"folders": [], "kinds": {}}
        rows = self.__conn.execute(
            "SELECT f.path, COUNT(c.id) AS chunks FROM files f JOIN chunks c ON c.file_id = f.id"
            " WHERE f.source = ? GROUP BY f.id", (source,)
        ).fetchall()
        folders: dict[str, int] = {}
        kinds: dict[str, int] = {}
        for row in rows:
            folder: str = "/".join(row["path"].strip("/").split("/")[:-1][:depth]) or "."
            folders[folder] = folders.get(folder, 0) + row["chunks"]
            kind: str = kind_of(row["path"])
            kinds[kind] = kinds.get(kind, 0) + 1
        return {
            "folders": sorted(folders.items(), key=lambda item: (-item[1], item[0])),
            "kinds": dict(sorted(kinds.items(), key=lambda item: -item[1]))
        }

    def search(self, query: str, vector: list[float] | None, model: str | None, limit: int,
               where: Filter | None = None) -> list[Hit]:
        """
            The passages that answer best: by keywords, and by meaning when the vector of the question is given
            (from the embedding model), among those the filter keeps. Only the vectors of that model are compared,
            those of another one mean nothing
        """
        if self.__conn is None:
            return []
        where = where or Filter()
        # None: whole sources. A filter on the files that keeps none has nothing to search
        files: list[int] | None = self.matching(where) if where.on_files else None
        if files is not None and not files:
            return []
        pool: int = limit * POOL
        scores: dict[int, float] = {}
        lists: list[list[int]] = [self.__by_keywords(query, pool, where.source, files)]
        if vector is not None and model:
            lists.append(self.__by_meaning(vector, model, pool, where.source, files))
        for ranked in lists:
            for rank, chunk_id in enumerate(ranked):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (RRF + rank + 1)
        best: list[int] = sorted(scores, key=scores.get, reverse=True)[:limit]
        if not best:
            return []
        rows = self.__conn.execute(
            "SELECT c.id, f.source, f.path, c.start_line, c.end_line, c.text, c.context, c.description FROM chunks c"
            " JOIN files f ON f.id = c.file_id WHERE c.id IN (%s)" % ",".join("?" * len(best)), best
        ).fetchall()
        by_id: dict[int, sqlite3.Row] = {row["id"]: row for row in rows}
        return [Hit(row["source"], row["path"], row["start_line"], row["end_line"], row["text"], round(scores[i], 4),
                    context=row["context"] or "", description=row["description"] or "")
                for i in best if (row := by_id.get(i)) is not None]

    def __by_keywords(self, query: str, pool: int, source: str | None, files: list[int] | None) -> list[int]:
        """ The ids of the passages holding the words of the question, the best match (BM25) first, in these files """
        words: list[str] = []
        for word in re.findall(r"\w+", query.lower()):
            if word not in STOPWORDS and word not in words:
                words.append(word)
        if not words:
            return []
        match: str = " OR ".join(f'"{word}"' for word in words[:QUERY_WORDS])
        where: str = ""
        params: list = [match]
        if source:
            where += " AND f.source = ?"
            params.append(source)
        if files is not None:
            # One parameter however many files: SQLite caps the number of "?" of a query
            where += " AND f.id IN (SELECT value FROM json_each(?))"
            params.append(json.dumps(files))
        rows = self.__conn.execute(
            "SELECT c.id FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid JOIN files f ON f.id = c.file_id"
            f" WHERE chunks_fts MATCH ?{where} ORDER BY bm25(chunks_fts, 1.0, 0.3) LIMIT ?",
            (*params, pool)
        ).fetchall()
        return [row[0] for row in rows]

    def __by_meaning(self, vector: list[float], model: str, pool: int, source: str | None,
                     files: list[int] | None) -> list[int]:
        """ The ids of the passages whose vector is the closest to the one of the question (cosine), best first """
        loaded = self.__load(model)
        if loaded is None:
            return []
        ids, sources, file_ids, matrix = loaded
        question: np.ndarray = np.asarray(vector, dtype=np.float32)
        norm: float = float(np.linalg.norm(question))
        if not norm or question.shape[0] != matrix.shape[1]:
            return []
        scores: np.ndarray = matrix @ (question / norm)
        if source:
            scores = np.where(sources == source, scores, -np.inf)
        if files is not None:
            scores = np.where(np.isin(file_ids, files), scores, -np.inf)
        top: np.ndarray = np.argpartition(-scores, min(pool, len(scores)) - 1)[:pool]
        top = top[np.argsort(-scores[top])]
        return [int(ids[i]) for i in top if np.isfinite(scores[i])]

    def __load(self, model: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
        """ The ids, sources, files and vectors of every passage embedded by this model, kept until the index changes """
        if self.__matrix is not None and self.__matrix[0] == model:
            return self.__matrix[1:]
        rows = self.__conn.execute(
            "SELECT c.id, f.source, c.file_id, c.vector FROM chunks c JOIN files f ON f.id = c.file_id"
            " JOIN sources s ON s.name = f.source WHERE c.vector IS NOT NULL AND s.model = ?", (model,)
        ).fetchall()
        # One model gives one length: a row of another one is a broken row
        size: int = len(rows[0]["vector"]) if rows else 0
        rows = [row for row in rows if len(row["vector"]) == size]
        if not rows:
            return None
        self.__matrix = (
            model,
            np.array([row["id"] for row in rows], dtype=np.int64),
            np.array([row["source"] for row in rows]),
            np.array([row["file_id"] for row in rows], dtype=np.int64),
            np.vstack([np.frombuffer(row["vector"], dtype=np.float32) for row in rows])
        )
        return self.__matrix[1:]

    @staticmethod
    def __delete(db: sqlite3.Connection, source: str, path: str) -> None:
        """ Remove a file and its passages (the search table has no cascade), inside the transaction of the caller """
        row = db.execute("SELECT id FROM files WHERE source = ? AND path = ?", (source, path)).fetchone()
        if row is None:
            return
        db.execute("DELETE FROM chunks_fts WHERE rowid IN (SELECT id FROM chunks WHERE file_id = ?)", (row[0],))
        db.execute("DELETE FROM files WHERE id = ?", (row[0],))

    def __open(self) -> sqlite3.Connection:
        """ The connection, the file and its tables created if needed """
        if self.__conn is None:
            self.__conn = sqlite3.connect(self.__path)
            self.__conn.row_factory = sqlite3.Row
            self.__conn.execute("PRAGMA foreign_keys = ON")
            self.__conn.executescript(SCHEMA)
            for table, column, kind in COLUMNS:
                if column not in {row["name"] for row in self.__conn.execute(f"PRAGMA table_info({table})")}:
                    self.__conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
            self.__conn.commit()
        return self.__conn
