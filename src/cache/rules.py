##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Rules of the semantic cache: which questions it may answer, and when two questions are the same one
##
## The meaning of two questions can be very close while they ask for different things: "17 × 23 ?" and "17 × 24 ?",
## "que fait config.py ?" and "que fait settings.py ?". An embedding reads the sentence, not its details: the details
## (numbers, files, names of the code) must be the same as well. And some questions have no answer that holds for
## long: the time ("quel jour sommes-nous ?") or the project as it is now ("que fait ce fichier ?").
## A question may come anywhere in a session, as long as it stands alone: "et pour la deuxième ?" means nothing without
## what came before. And an answer is only stored while the session is clean: once the model read the project, what it
## says next may lean on it, even to a question that stands alone
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

# What leans on what was said before: a question that starts by going on ("et en JavaScript ?"), or that points back
# at something ("explique-le", "le deuxième", "ta réponse", "that one"). Matched without accents
CONNECTOR: re.Pattern = re.compile(
    r"^\W*(?:et|mais|aussi|alors|donc|du coup|sinon|d'accord|puis|ensuite|and|but|also|so|then|ok(?:ay)?"
    r"|what about|how about)\b",
    re.IGNORECASE
)
# An ordinal points back alone ("et le deuxième ?"), or at a part of an answer ("le deuxième exemple"): never in "le
# dernier commit git", "le premier élément d'une liste"
ORDINAL: str = r"(?:meme|memes|premier|premiere|deuxieme|second|seconde|troisieme|dernier|derniere|precedent|precedente" \
               r"|suivant|suivante|autre)"
PART: str = r"(?:exemple|exemples|point|cas|option|solution|methode|version|lien|resultat|etape|reponse|code|bout)"
BACKWARD: re.Pattern = re.compile(
    rf"\b(?:ca|cela|ceci|celui(?:-ci|-la)?|celle(?:-ci|-la)?|ceux(?:-ci|-la)?|celles(?:-ci|-la)?"
    rf"|(?:le|la|les|l') ?{ORDINAL}(?=\s*(?:[?.!,;:]|$))|(?:le|la|les|l') ?{ORDINAL}s? {PART}"
    r"|ci-dessus|au-dessus|plus haut|precedemment|tout a l'heure|encore|pareil"
    r"|ta (?:reponse|solution|version|methode)|ton (?:code|exemple|script|programme)|tes (?:exemples|reponses)"
    # "explique-le", "corrige-la": what? "Explique-moi les décorateurs" says it
    r"|(?:dis|explique|montre|corrige|refais|ameliore|detaille|reformule|traduis|continue)-(?:le|la|les)(?:-moi)?"
    r"|that one|this one|those|these|the (?:same|first|second|third|last|previous|next|above)|above|again"
    r"|your (?:answer|code|solution|example)|it|them)\b",
    re.IGNORECASE
)
# Fewer words than this mean nothing alone: "pourquoi ?", "explique plus", "un exemple"
MIN_WORDS: int = 3

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

def same_text(first: str, second: str) -> bool:
    """ Whether two questions are written the same, but for their case, accents, punctuation and spaces """
    def bare(text: str) -> str:
        return " ".join(re.sub(r"[^\w]+", " ", plain(text)).split())
    return bare(first) == bare(second)

def same_specifics(first: str, second: str) -> bool:
    """ Whether two questions ask about the same numbers, files and names of the code """
    return specifics(first) == specifics(second)

def timely(question: str) -> bool:
    """ Whether the answer depends on the time it is asked: never given again """
    return bool(TIMELY.search(plain(question)))

def situated(question: str) -> bool:
    """ Whether the answer depends on the project as it is now: never given again """
    return bool(SITUATED.search(plain(question)))

def standalone(question: str) -> bool:
    """ Whether a question means something without what was said before it in the session """
    text: str = plain(question)
    return len(text.split()) >= MIN_WORDS and not CONNECTOR.search(text) and not BACKWARD.search(text)

def clean(history: list[dict], tools: frozenset[str] | set[str]) -> bool:
    """
        Whether the model read nothing of the project in the session yet: no call to a tool but those given (their
        sources are the knowledge base, not the project). history is the session in the format of the model API
    """
    return all(call.get("function", {}).get("name") in tools
               for message in history for call in message.get("tool_calls") or [])

def personal(answer: str, name: str | None) -> bool:
    """ Whether an answer names the user it was given to ("Bonjour Ada, ..."): never given to another one """
    return bool(name) and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", answer, re.IGNORECASE) is not None

def why_not(question: str) -> str | None:
    """
        Why a question may not be answered from the cache, nor its answer stored: "followup" (it leans on what was said
        before), "timely", "project". None if it may
    """
    if not standalone(question):
        return "followup"
    if timely(question):
        return "timely"
    if situated(question):
        return "project"
    return None
