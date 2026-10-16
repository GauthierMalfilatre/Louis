##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Rules of the semantic cache: which questions it may answer, and when two questions are the same one
##
## The meaning of two questions can be very close while they ask for different things: "17 × 23 ?" and "17 × 24 ?",
## "que fait config.py ?" and "que fait settings.py ?". An embedding reads the sentence, not its details: the details
## (numbers, files, names of the code) must be the same as well. And some questions have no answer that holds for
## long: the time ("quel jour sommes-nous ?") or the project as it is now ("que fait ce fichier ?")
##
from app.constants import CITED_FILE
import re
import unicodedata

# A number, never a piece of a word or of a version already caught as a file (v2.py): 17, 3.13, 0,5
NUMBER: re.Pattern = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*(?![\w])")
# A name of the code: snake_case, camelCase, PascalCase with two humps at least (a French word has none), a call, or
# what the user put between backquotes
IDENTIFIER: re.Pattern = re.compile(
    r"\b(?:[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+|[a-z]+[A-Z][A-Za-z0-9]*|[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*)\b"
    r"|\b(\w+)\(\)|`([^`\n]{1,80})`"
)

# What depends on the time: the answer of today is wrong tomorrow. Matched without accents
TIMELY: re.Pattern = re.compile(
    r"\b(?:aujourd'?hui|maintenant|actuellement|en ce moment|hier|demain|ce matin|ce soir|cette semaine|ce mois"
    r"|cette annee|quelle heure|quel jour|quelle date|la date|derniere version|dernieres? nouvelles?|recemment"
    r"|today|now|currently|yesterday|tomorrow|tonight|this (?:week|month|year)|what time|what day|latest|recently)\b",
    re.IGNORECASE
)
# What depends on the project as it is now: its files change, the answer of before may no longer hold
SITUATED: re.Pattern = re.compile(
    r"\b(?:ce projet|mon projet|notre projet|ce depot|mon depot|ce fichier|mon fichier|ce dossier|mon dossier|ce code"
    r"|mon code|notre code|ici|this (?:project|repo|repository|file|folder|directory|code)"
    r"|my (?:project|repo|repository|file|folder|code)|our (?:project|code)|here)\b",
    re.IGNORECASE
)

def plain(text: str) -> str:
    """ A text to look for words in: lower case, without accents, with straight apostrophes """
    text = unicodedata.normalize("NFD", text.lower().replace("’", "'"))
    return "".join(char for char in text if unicodedata.category(char) != "Mn")

def specifics(text: str) -> frozenset[str]:
    """
        The details of a question an embedding reads past: its numbers (0,5 is 0.5), the files it names and the names
        of the code. Never their case: the user types config.py or Config.py for the same file
    """
    found: set[str] = {f"n:{number.replace(',', '.')}" for number in NUMBER.findall(text)}
    found |= {f"f:{match.group(1).lower()}" for match in CITED_FILE.finditer(text)}
    for match in IDENTIFIER.finditer(text):
        name: str = match.group(2) or match.group(1) or match.group(0)
        # A file between backquotes is already a file
        if not CITED_FILE.fullmatch(name):
            found.add(f"i:{name.strip().lower()}")
    return frozenset(found)

def same_specifics(first: str, second: str) -> bool:
    """ Whether two questions ask about the same numbers, files and names of the code """
    return specifics(first) == specifics(second)

def timely(question: str) -> bool:
    """ Whether the answer depends on the time it is asked: never given again """
    return bool(TIMELY.search(plain(question)))

def situated(question: str) -> bool:
    """ Whether the answer depends on the project as it is now: never given again """
    return bool(SITUATED.search(plain(question)))

def first(messages: list) -> bool:
    """ Whether the user said nothing yet in the session (its messages, before the question is added) """
    return not any(message.role == "user" for message in messages)

def why_not(question: str, is_first: bool, scope: str) -> str | None:
    """
        Why a question may not be answered from the cache, nor its answer stored: "followup" (not the first message of
        the session while the scope is "first"), "timely", "project". None if it may
    """
    if scope == "first" and not is_first:
        return "followup"
    if timely(question):
        return "timely"
    if situated(question):
        return "project"
    return None
