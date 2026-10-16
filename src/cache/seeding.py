##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Seed of the semantic cache: answers written by the team, for a cache that is useful from the first question
##
## The files of cache/seed/ (*.jsonl), one answer per line, with the questions it answers in several words:
##   {"questions": ["Comment indexer un dossier ?", "Comment ajouter de la documentation à Louis ?"], "answer": "..."}
## They are read in the order of their names. Their version is the hash of what they hold: the cache stores their
## questions again only when it changes. The answers are never checked by a model: they must be right, and say what
## Louis does whatever the session (no "ce fichier", no date)
##
from logger.logger import log
import hashlib
import json
import os

SEED_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed")

def load(folder: str | None = SEED_DIR) -> tuple[str, list[tuple[str, str]]]:
    """
        The version of the seed files of the folder, and their (question, answer) pairs, one per question. None, or a
        folder that does not exist: no seed (its version is that of nothing, the seed stored before is removed)
    """
    digest = hashlib.sha256()
    pairs: list[tuple[str, str]] = []
    names: list[str] = sorted(name for name in os.listdir(folder) if name.endswith(".jsonl")) \
        if folder and os.path.isdir(folder) else []
    for name in names:
        with open(os.path.join(folder, name), encoding="utf-8") as file:
            content: str = file.read()
        digest.update(name.encode("utf-8") + b"\0" + content.encode("utf-8") + b"\0")
        for number, line in enumerate(content.splitlines(), 1):
            if not line.strip():
                continue
            try:
                item: dict = json.loads(line)
                answer: str = item["answer"].strip()
                questions: list[str] = [question.strip() for question in item["questions"] if question.strip()]
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                log.warning(f"[cache] {name}:{number} left out of the seed: {type(e).__name__}: {e}")
                continue
            pairs.extend((question, answer) for question in questions if answer)
    return digest.hexdigest()[:12], pairs
