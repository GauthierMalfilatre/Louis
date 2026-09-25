##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Context window: what the model sees of a session, cut down before it overflows
##
from config.prompt import NUDGE_PROMPT
import json

# Characters of the history (as JSON, with the tools) for a token of qwen3: measured on Ollama, 3.91 to 3.93
CHARS_PER_TOKEN: float = 3.9

# Past this share of the context, the old tool results are cut down, until it is back under TARGET: the rest is left
# for the reply (a whole file written by write_file), and the cut is done seldom, a block at a time
TRIGGER: float = 0.70
TARGET : float = 0.45

# What stays of a tool result cut down: its first lines, the path of a file, a tree, a docstring...
PREVIEW_LINES: int = 3
PREVIEW_CHARS: int = 200
# Shorter than this, a result stays whole: a tree, search results, an edit are small, and often the plan of the task
# (the files to read). The files read take the room: cutting them down is enough
STUB_MIN_CHARS: int = 2000

# A single tool result may take this share of the context at most (a whole big file, 200 search results...), and
# the results of all the calls of a reply together ROUND at most: the window never cuts the round being worked on,
# it must fit under TRIGGER with the system prompt and the tools
MAX_RESULT: float = 0.25
ROUND     : float = 0.40

def tokens(characters: int) -> int:
    """ The tokens of text as long as that, for the model """
    return round(characters / CHARS_PER_TOKEN)

def size_of(message: dict) -> int:
    """ The characters of a message, as it is sent """
    return len(json.dumps(message, ensure_ascii=False))

def stub(content: str) -> str:
    """ A tool result cut down to its first lines, with what the model must know: it can ask for it again """
    lines: list[str] = content.splitlines()
    kept: list[str] = []
    for line in lines[:PREVIEW_LINES]:
        if sum(len(k) for k in kept) + len(line) > PREVIEW_CHARS:
            break
        kept.append(line)
    return "\n".join(kept + [
        f"[… {len(lines) - len(kept)} lignes retirées pour faire de la place dans le contexte : "
        "relance l'outil si tu en as encore besoin.]"
    ])

def share(text: str, size: int) -> float:
    """ The share of a context of size tokens that text takes """
    return tokens(len(text)) / size

def capped(result: str, size: int, most: float = MAX_RESULT) -> str:
    """ A tool result cut to a share of a context of size tokens, at the end of a line, with a word on the rest """
    room: int = round(size * most * CHARS_PER_TOKEN)
    if len(result) <= room:
        return result
    cut: int = result.rfind("\n", 0, room)
    cut = cut if cut > 0 else room
    left: int = result.count("\n", cut) + 1
    return (result[:cut] + f"\n[… {left} lignes de plus non affichées : ce résultat prenait trop de place dans le "
            "contexte. Demande une partie plus petite (start_line et end_line pour cat_file, un motif ou un dossier "
            "plus précis pour search).]")

class ContextWindow:
    """
        What the model sees of a session: all of it while it fits, then its old tool results cut down to their first
        lines, and at last its oldest exchanges left out. Left to itself, Ollama drops the start of the conversation
        (the request of the user first), and even cuts in the middle of a message: here the system prompt, the
        request and the last round of calls always stay, and the calls made before as long as there is room (the
        model knows what it did).
        The cut only moves forward, a block at a time: between two cuts, what is sent starts the same, and Ollama
        reuses its cache instead of reading the whole conversation again
    """
    def __init__(self, size: int, tools: list[dict]):
        """ Init the window of a context of size tokens, with these tools in every request """
        self.__size   : int = size
        self.__fixed  : int = len(json.dumps(tools, ensure_ascii=False))
        # The tool results before this index are cut down, the messages from 1 to this one are left out (but the
        # system prompt and the request being answered)
        self.__stubbed: int = 0
        self.__hidden : int = 1

    @property
    def size(self) -> int:
        """ The tokens the model sees at once """
        return self.__size

    def reset(self) -> None:
        """ Another session: nothing of it is cut yet """
        self.__stubbed, self.__hidden = 0, 1

    def tokens(self, messages: list[dict]) -> int:
        """ The tokens of these messages, sent with the tools """
        return tokens(self.__fixed + sum(size_of(message) for message in messages))

    def view(self, history: list[dict]) -> tuple[list[dict], dict | None]:
        """
            The messages to send for this history, and what was cut this time: {"results", "dropped"}, the tool
            results cut down and the messages left out, or None if nothing more was
        """
        # The last reply of the model, and the results of its calls after it, are what it works on: never cut
        last: int = max((i for i, message in enumerate(history) if message["role"] == "assistant"), default=len(history))
        # The request being answered is never left out (the nudge is no request)
        request: int = max(
            (i for i, message in enumerate(history) if message["role"] == "user" and message["content"] != NUDGE_PROMPT),
            default=len(history)
        )
        messages: list[dict | None] = [self.__shown(message, i, request) for i, message in enumerate(history)]
        used: int = self.__fixed + sum(size_of(message) for message in messages if message is not None)
        if tokens(used) <= self.__size * TRIGGER:
            return [message for message in messages if message is not None], None

        target: float = self.__size * TARGET
        results: int = 0
        while tokens(used) > target and self.__stubbed < last:
            i: int = self.__stubbed
            self.__stubbed += 1
            if messages[i] is None or messages[i]["role"] != "tool" or len(history[i]["content"]) < STUB_MIN_CHARS:
                continue
            shown: dict = self.__shown(history[i], i, request)
            used += size_of(shown) - size_of(messages[i])
            messages[i] = shown
            results += 1

        dropped: int = 0
        # Still too long: the oldest messages go, a whole exchange or round of calls at a time (a reply of the model
        # with the results of its calls), the oldest turns first, then the first rounds of this one
        while tokens(used) > target and self.__hidden < last:
            end: int = next(i for i in range(self.__hidden + 1, last + 1) if history[i]["role"] != "tool")
            for i in range(self.__hidden, end):
                if messages[i] is not None and i != request and history[i]["role"] != "system":
                    used -= size_of(messages[i])
                    messages[i] = None
                    dropped += 1
            self.__hidden = end
        cut: dict | None = {"results": results, "dropped": dropped} if results or dropped else None
        return [message for message in messages if message is not None], cut

    def __shown(self, message: dict, index: int, request: int) -> dict | None:
        """ A message as the model sees it now: left out, cut down, or whole """
        if message["role"] != "system" and index != request and 1 <= index < self.__hidden:
            return None
        if message["role"] == "tool" and index < self.__stubbed and len(message["content"]) >= STUB_MIN_CHARS:
            return {**message, "content": stub(message["content"])}
        return message
