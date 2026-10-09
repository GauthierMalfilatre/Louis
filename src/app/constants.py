##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Constants of the app: what it tells the model and the user, the limits of a turn, the check of a draft
##
from events.event_list import CHAT_TEXT, CHAT_THINKING, CHAT_REPLY, MODEL_CALL, TOOL_CALL_STARTED, TOOL_CALL_ENDED
from events.event_list import EVAL_SCORED, EVAL_REPORT
import re

# A reply that says what the model is about to do, in French or English. In French, "je vais" must lead to
# a verb ("je vais créer", "je vais d'abord lire"): "je vais bien" is only small talk, as "let me know" is.
# "Vérifions game.py" too, but only at the start of a sentence: "ici, nous vérifions que..." explains the code
ANNOUNCE: re.Pattern = re.compile(
    r"\b(?:je vais (?:[\w']+ ){0,2}?[\w']+(?:er|ir|re|oir)|je m'apprête à|laisse-moi"
    r"|i will|i'll|let me(?! know)|let's|i am going to|i'm going to)\b"
    r"|(?:^|(?<=[.!?:] ))(?:vérifi|regard|lis|ajout|corrige|modifi|examin|cherch|cré|consult|voy|commenç"
    r"|analys|ouvr|test|remplaç|renomm)ons\b",
    re.IGNORECASE | re.MULTILINE
)

# Logged whole elsewhere (the reply and its stats by the model, the tool calls by __call, the judgments by the
# evaluator): not once more per event
UNLOGGED: frozenset[str] = frozenset({
    CHAT_TEXT, CHAT_THINKING, CHAT_REPLY, MODEL_CALL, TOOL_CALL_STARTED, TOOL_CALL_ENDED, EVAL_SCORED, EVAL_REPORT
})

# Where the context Louis adds starts, after the system prompt
CONTEXT: str = "\n\n# Contexte\n"

CANCELLED_TOOL: str = "Annulé : l'utilisateur a interrompu Louis avant la fin de cet outil."

# The same call (tool and arguments) made this many times already for a message is refused: the model goes round in
# circles. After MAX_REFUSED refused calls, the turn stops
SAME_CALLS : int = 2
MAX_REFUSED: int = 3
REPEATED_CALL: str = (
    "Erreur : tu as déjà fait exactement cet appel 2 fois pour cette demande. N'en refais pas un troisième : "
    "utilise ce que tu sais déjà, lis une autre partie, ou réponds à l'utilisateur. S'il n'a pas marché, dis-lui "
    "ce qui a échoué : ne dis jamais avoir fait ce qui n'a pas été fait."
)
# The model sometimes asks for dozens of calls at once, often the same ones again (a list gone wrong): the first
# MAX_CALLS different ones are kept, the others never made. And the results of a round, never cut by the window, must
# still have this share of the context for one more call to run
MAX_CALLS: int   = 6
MIN_ROOM : float = 0.05
IGNORED_CALLS: str = (
    "\n[{} autres appels de ta réponse ont été ignorés (en double, ou trop nombreux à la fois) : "
    "refais ceux qui manquent dans ta prochaine réponse.]"
)
NO_ROOM: str = (
    "Erreur : les résultats de ta réponse prennent déjà trop de place dans le contexte : cet appel n'a pas été fait. "
    "Refais-le dans ta prochaine réponse."
)
EMPTY_MESSAGE: str = "Louis n'a rien répondu, deux fois : le modèle a sans doute appelé un outil qui n'existe pas ici. "
# Why, when the session called tools this version of Louis does not have: the model calls them again
GONE_TOOLS: str = (
    "Cette session a utilisé des outils absents de cette version de Louis (une autre branche ?), et le modèle les "
    "appelle encore : {tools}. Lance Louis depuis une version qui les a, ou repars d'une session neuve avec /clear."
)
LOOP_MESSAGE: str = (
    "Louis tournait en rond (les mêmes appels d'outils, encore et encore) : arrêté. Reformule ou découpe la demande."
)

# What the chat model reads of the messages it sums up when they leave its context: each one cut to these characters
# (a file read is what it learns from: its facts are often far from its start), and all of them to this share of its
# context. The summaries added up are merged into a shorter one past SUMMARY_CHARS
SUMMARY_MESSAGE: int   = 2000
SUMMARY_RESULT : int   = 6000
SUMMARY_SHARE  : float = 0.4
SUMMARY_CHARS  : int   = 3000

# Calls of a tool the guard refuses in a turn before the tool is withdrawn until the next message: the model
# may redo a call without the sensitive data once, but qwen3 can also ask the same one again and again
REFUSED_CALLS: int = 2

# What the model says of its draft in the reasoning loop (reason.verify): JSON, for no text to be read into a verdict.
# Never one of the schemas of /json: the user does not ask for it. Ollama has the fields written in this order: the
# claims checked again first, the verdict last. Asked first, the verdict is given before anything is looked at, and
# the rest only backs it up (ok in 11 tokens for 17 × 23 = 381). Each claim gives where it was found: checked again
# without one, the model finds a file it never read in its own draft. A few problems, each one short: enough to fix them
MAX_CHECKS   : int = 6
MAX_PROBLEMS : int = 5
PROBLEM_CHARS: int = 300
CRITIQUE: dict = {
    "type": "object",
    "properties": {
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string", "description": "une affirmation importante de la réponse (fait, calcul, "
                                                              "chemin, valeur, action faite)"},
                    "source": {"type": "string", "description": "où tu la retrouves : le résultat d'un outil (lequel, et "
                                                               "ce qu'il dit), le calcul refait pas à pas, ou "
                                                               "\"introuvable\". La réponse vérifiée n'est jamais une source"},
                    "holds": {"type": "boolean", "description": "true seulement si la source la confirme"}
                },
                "required": ["claim", "source", "holds"],
                "additionalProperties": False
            },
            "minItems": 1,
            "maxItems": MAX_CHECKS,
            "description": "chaque affirmation importante de la réponse, vérifiée de nouveau"
        },
        "problems": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": MAX_PROBLEMS,
            "description": "les vrais problèmes trouvés par ces vérifications, une phrase chacun, [] s'il n'y en a aucun"
        },
        "ok": {"type": "boolean", "description": "true seulement si aucune vérification n'a trouvé de problème"}
    },
    "required": ["checks", "problems", "ok"],
    "additionalProperties": False
}

# A file a draft names: a path with the extension of a file of code, of data or of documentation. Never a piece of a
# URL or of a longer path, nor a number (1.2, 3.13)
CITED_FILE: re.Pattern = re.compile(
    r"(?<![\w/.:-])((?:[\w-]+/)*[\w-]+\.(?:py|pyi|js|jsx|ts|tsx|json|jsonl|md|txt|rst|ya?ml|toml|ini|cfg|co|c|h|cpp|hpp|cc"
    r"|go|rs|java|kt|rb|php|sh|bash|html|css|scss|sql|csv|xml|lock))(?![\w/-])"
)
UNSOURCED: str = (
    "{path} : aucun outil ne l'a lu, listé ni écrit dans cette session, ce que la réponse en dit n'a pas de source. "
    "Lis-le avant d'en parler, ou dis que tu ne l'as pas lu."
)
