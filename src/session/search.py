##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Search: the sessions of a user that talked about something, by the meaning of what the scribe wrote of them
##
from rag.embedder import Embedder, EmbedError
from session.database import Database
from logger.logger import log
import numpy as np
import unicodedata

# How close the meaning of a session must be to the question. Measured with nomic-embed-text on short French sessions:
# ~0.60 to 0.74 for those about it, ~0.50 to 0.58 for the others, whatever the question. So a session is found when it
# stands out: the closest one STANDS_OUT above the median of all of them (else none is about the question: "recette de
# cuisine"), and the others as close as CLOSE_TO_BEST to it. With fewer than 3 sessions, no median: ALONE at least
MIN_MEANING  : float = 0.55
STANDS_OUT   : float = 0.04
CLOSE_TO_BEST: float = 0.06
ALONE        : float = 0.62
# What the words of the question found in a session add to its meaning: a name of a file, of a function, typed as it is
WORDS_WEIGHT: float = 0.3
MOST: int = 8
# Words found in every session: never a reason to find one
STOPWORDS: frozenset[str] = frozenset(
    "le la les un une des du de d l au aux et ou a en dans sur sous pour par avec sans ce cet cette ces mon ma mes ton ta "
    "tes son sa ses qui que quoi comment est sont fait faire je tu il on nous vous ils the of to in on for with and or "
    "is are how what".split()
)

def plain(text: str) -> str:
    """ A text to compare words in: lower case, without accents """
    return "".join(char for char in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(char) != "Mn")

def words(query: str) -> list[str]:
    """ The words of a question worth looking for: two letters at least """
    return [word for word in plain(query).replace("?", " ").replace("'", " ").split()
            if len(word) >= 2 and word not in STOPWORDS]

def close(meanings: list[float]) -> float:
    """ How close to the question a session must be to be found by its meaning, among these (1.0: none is) """
    if not meanings:
        return 1.0
    best: float = max(meanings)
    if len(meanings) < 3:
        return max(ALONE, MIN_MEANING)
    if best - float(np.median(meanings)) < STANDS_OUT:
        return 1.0
    return max(MIN_MEANING, best - CLOSE_TO_BEST)

def find(db: Database, user_id: int, query: str, embedder: Embedder | None, here: str,
         current: int | None = None) -> tuple[list[dict], str]:
    """
        The sessions of the user about the question, the closest first, and how they were found: "meaning" (the vectors
        the scribe saved, and the words) or "words" (no vector, or the embedding model does not answer)
    """
    rows = db.fetchall(
        "SELECT s.id, s.cwd, s.created_at, s.title, s.summary, s.vector, "
        "(SELECT content FROM messages m WHERE m.session_id = s.id AND m.role = 'user' ORDER BY m.id LIMIT 1) AS first, "
        "(SELECT group_concat(content, ' ') FROM messages m WHERE m.session_id = s.id AND m.role = 'user') AS asked "
        "FROM sessions s WHERE s.user_id = ? ORDER BY s.id DESC",
        (user_id,)
    )
    wanted: list[str] = words(query)
    question: np.ndarray | None = None
    if embedder is not None and any(row["vector"] for row in rows):
        try:
            vector: np.ndarray = np.asarray(embedder.query(query), dtype=np.float32)
            norm: float = float(np.linalg.norm(vector))
            question = vector / norm if norm else None
        except EmbedError as e:
            log.warning(f"[search] by words only: {e.message}")

    meanings: dict[int, float] = {}
    if question is not None:
        for row in rows:
            stored: np.ndarray | None = np.frombuffer(row["vector"], dtype=np.float32) if row["vector"] else None
            if stored is not None and stored.shape == question.shape:
                meanings[row["id"]] = float(np.dot(question, stored))
    least: float = close(list(meanings.values()))

    found: list[dict] = []
    for row in rows:
        text: str = plain(" ".join(part for part in (row["title"], row["summary"], row["asked"]) if part))
        share: float = sum(word in text for word in wanted) / len(wanted) if wanted else 0.0
        meaning: float | None = meanings.get(row["id"])
        if share == 0 and (meaning is None or meaning < least):
            continue
        found.append({
            "id": row["id"], "title": row["title"], "summary": row["summary"], "first_message": row["first"],
            "cwd": row["cwd"], "here": row["cwd"] == here, "current": row["id"] == current,
            "created_at": row["created_at"],
            "score": round((meaning or 0.0) + WORDS_WEIGHT * share if question is not None else share, 3),
        })
    found.sort(key=lambda session: session["score"], reverse=True)
    return found[:MOST], "meaning" if question is not None else "words"
