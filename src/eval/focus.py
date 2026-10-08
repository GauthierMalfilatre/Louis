##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Focus: the passages of the sources each claim is about, for the judge to read those instead of whole files
##
## A small judge does not find a line in a long file: measured on a claim of an answer and the file it read
## (app/app.py, 21 000 characters), qwen3:4b-instruct and qwen3:8b said "unverifiable" whatever the claim, and
## "supported" with the right quote once given the 600 characters around it. So, as FActScore does, the passages each
## claim is about are looked for first: the sources cut into windows of lines, ranked for each claim by its words
## (the identifiers cut in their parts: SAME_CALLS is "same" and "calls"), then, when the reranker of the knowledge base
## is there, read again with the claim by its cross-encoder (it reads French and English: a claim in French, a comment
## in English). The windows kept go to the judge in the order of their source, under its number
##
from collections.abc import Callable
from dataclasses import dataclass
import math
import re

# Sources shorter than this go to the judge whole
FOCUS_CHARS: int = 4000
# The windows: their lines, and the lines between the starts of two of them (they overlap: a fact cut by one is
# whole in the next)
WINDOW_LINES: int = 20
STEP_LINES  : int = 10
# Windows ranked by the words of a claim that the cross-encoder reads again, and those kept for each claim
POOL     : int = 6
PER_CLAIM: int = 2

NOTHING: str = "(rien dans cette source ne semble concerner les affirmations)"
GAP    : str = "\n[…]\n"

@dataclass(frozen=True, slots=True)
class Window:
    """ Lines start to end (excluded) of a source, its index from 0 """
    source: int
    start : int
    end   : int
    text  : str

def windows(texts: list[str]) -> list[Window]:
    """ The windows of lines of the sources: overlapping, the last one of a source up to its end """
    found: list[Window] = []
    for index, text in enumerate(texts):
        lines: list[str] = text.splitlines()
        for start in range(0, max(1, len(lines) - WINDOW_LINES + STEP_LINES), STEP_LINES):
            end: int = min(len(lines), start + WINDOW_LINES)
            found.append(Window(index, start, end, "\n".join(lines[start:end])))
    return found

def terms(text: str) -> list[str]:
    """ The words of a text that tell what it is about: identifiers cut in their parts, numbers kept, case ignored """
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    words: list[str] = re.findall(r"[^\W_]+", text.lower())
    return [word for word in words if len(word) >= 3 or word.isdigit()]

def by_words(query: str, found: list[Window]) -> list[float]:
    """
        How much each window is about the query by its words: the rare words of the sources count more (idf), and a
        word counts once per window
    """
    sets: list[set[str]] = [set(terms(window.text)) for window in found]
    asked: set[str] = set(terms(query))
    df: dict[str, int] = {word: sum(1 for words in sets if word in words) for word in asked}
    idf: dict[str, float] = {word: math.log(1 + len(found) / count) for word, count in df.items() if count}
    return [sum(idf.get(word, 0.0) for word in words & asked) for words in sets]

def focus(texts: list[str], claims: list[str], rerank: Callable[[str, list[str]], list[float]] | None = None) -> list[str]:
    """
        The sources as the judge reads them: whole when they are short, else for each one the windows the claims are
        about (merged when they touch), or a line saying none is. rerank scores texts against a claim (the cross-encoder):
        None, or one that fails, and the words alone choose
    """
    if sum(len(text) for text in texts) <= FOCUS_CHARS or not claims:
        return texts
    found: list[Window] = windows(texts)
    kept: set[int] = set()
    for claim in claims:
        scores: list[float] = by_words(claim, found)
        pool: list[int] = sorted(range(len(found)), key=lambda i: -scores[i])[:POOL]
        if rerank is not None:
            try:
                read: list[float] = rerank(claim, [found[i].text for i in pool])
                pool = [i for _, i in sorted(zip(read, pool), key=lambda pair: -pair[0])]
            except Exception:
                rerank = None
        kept.update(pool[:PER_CLAIM])

    focused: list[str] = []
    for index, text in enumerate(texts):
        lines: list[str] = text.splitlines()
        spans: list[list[int]] = []
        for window in sorted((found[i] for i in kept if found[i].source == index), key=lambda w: w.start):
            if spans and window.start <= spans[-1][1]:
                spans[-1][1] = max(spans[-1][1], window.end)
            else:
                spans.append([window.start, window.end])
        if not spans:
            focused.append(NOTHING)
            continue
        parts: list[str] = ["\n".join(lines[start:end]) for start, end in spans]
        focused.append(("[…]\n" if spans[0][0] > 0 else "") + GAP.join(parts) + ("\n[…]" if spans[-1][1] < len(lines) else ""))
    return focused
