##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Context window: what the model sees of a session, cut down before it overflows
##
from config.prompt import NUDGE_PROMPT, EMPTY_PROMPT, REVISE_PROMPT, SUMMARY_ASKED, SUMMARY_TITLE
from collections.abc import Callable
import json

# Characters of the history (as JSON, with the tools) for a token of qwen3: measured on Ollama, 3.91 to 3.93. On text
# only: logs, numbers or JSON take far more tokens (a log of louis: 2.2), so the window follows what Ollama counts
CHARS_PER_TOKEN: float = 3.9
# The fewest characters a token may stand for, whatever Ollama counted: a wrong count never empties the context
MIN_CHARS_PER_TOKEN: float = 1.5

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

def share(text: str, size: int, ratio: float = CHARS_PER_TOKEN) -> float:
    """ The share of a context of size tokens that text takes, at ratio characters a token """
    return len(text) / ratio / size

def capped(result: str, size: int, most: float = MAX_RESULT, ratio: float = CHARS_PER_TOKEN) -> str:
    """ A tool result cut to a share of a context of size tokens, at the end of a line, with a word on the rest """
    room: int = round(size * most * ratio)
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
        model knows what it did). With summarize, what is left out is summed up by it (the chat model), and the summary
        put right after the system prompt: the model goes on knowing what was asked, learnt and done.
        The cut only moves forward, a block at a time: between two cuts, what is sent starts the same, and Ollama
        reuses its cache instead of reading the whole conversation again
    """
    def __init__(self, size: int, tools: list[dict], summarize: Callable[[str, list[dict]], str | None] | None = None):
        """
            Init the window of a context of size tokens, with these tools in every request. summarize(previous, left):
            the summary of the messages left out, with the one made before, or None to leave them out only
        """
        self.__size   : int = size
        self.__fixed  : int = len(json.dumps(tools, ensure_ascii=False))
        self.__summarize: Callable[[str, list[dict]], str | None] | None = summarize
        # The summary of what was left out, and the index it goes to: the messages from it to __hidden are not in it yet
        self.__summary: str = ""
        self.__summed : int = 1
        # The tool results before this index are cut down, the messages from 1 to this one are left out (but the
        # system prompt and the request being answered)
        self.__stubbed: int = 0
        self.__hidden : int = 1
        # Characters for a token, as Ollama counted the last request: under CHARS_PER_TOKEN when the context holds
        # dense text, where the estimate would let it overflow without cutting anything
        self.__ratio  : float = CHARS_PER_TOKEN
        # The characters of the last messages view gave, with the tools: what Ollama counted next
        self.__sent   : int = 0

    @property
    def size(self) -> int:
        """ The tokens the model sees at once """
        return self.__size

    def set_tools(self, tools: list[dict]) -> None:
        """ The tools sent in every request changed: they take their room in the context from now on """
        self.__fixed = len(json.dumps(tools, ensure_ascii=False))

    @property
    def ratio(self) -> float:
        """ The characters a token stands for, as last measured """
        return self.__ratio

    def reset(self) -> None:
        """ Another session: nothing of it is cut yet, nor measured """
        self.__stubbed, self.__hidden = 0, 1
        self.__ratio, self.__sent = CHARS_PER_TOKEN, 0
        self.__summary, self.__summed = "", 1

    def measured(self, prompt_tokens: int) -> None:
        """
            Ollama counted the prompt of the last request: the estimate follows it. Never fewer tokens than
            CHARS_PER_TOKEN gives, the context is only ever cut sooner for it
        """
        if prompt_tokens > 0 and self.__sent > 0:
            self.__ratio = max(MIN_CHARS_PER_TOKEN, min(CHARS_PER_TOKEN, self.__sent / prompt_tokens))

    def __count(self, characters: int) -> int:
        """ The tokens of characters of the history, at the ratio measured """
        return round(characters / self.__ratio)

    def tokens(self, messages: list[dict]) -> int:
        """ The tokens of these messages, sent with the tools """
        return self.__count(self.__fixed + sum(size_of(message) for message in messages))

    def view(self, history: list[dict], summarize: bool = True) -> tuple[list[dict], dict | None]:
        """
            The messages to send for this history, and what was cut this time: {"results", "dropped", "summarized"},
            the tool results cut down, the messages left out, and whether what was left out was summed up, or None if
            nothing more was. summarize False never asks the model (an estimate): what is left out then is summed up
            by the next view
        """
        # The last reply of the model, and the results of its calls after it, are what it works on: never cut
        last: int = max((i for i, message in enumerate(history) if message["role"] == "assistant"), default=len(history))
        # The request being answered is never left out (the nudge, and the problems of a draft to fix, are no request)
        request: int = max(
            (i for i, message in enumerate(history) if message["role"] == "user" and message["content"] != NUDGE_PROMPT
             and not message["content"].startswith(EMPTY_PROMPT.split("{")[0])
             and not message["content"].startswith(REVISE_PROMPT.split("{")[0])),
            default=len(history)
        )
        messages: list[dict | None] = [self.__shown(message, i, request) for i, message in enumerate(history)]
        used: int = self.__fixed + sum(size_of(message) for message in messages if message is not None) + self.__extra()
        results: int = 0
        dropped: int = 0
        if self.__count(used) > self.__size * TRIGGER:
            results, dropped = self.__cut(history, messages, used, last, request)
        summarized: bool = summarize and self.__sum_up(history, request)
        shown: list[dict] = self.__with_summary([message for message in messages if message is not None])
        self.__sent = self.__fixed + sum(size_of(message) for message in shown)
        cut: dict | None = {"results": results, "dropped": dropped, "summarized": summarized} \
            if results or dropped or summarized else None
        return shown, cut

    def __cut(self, history: list[dict], messages: list[dict | None], used: int, last: int, request: int) -> tuple[int, int]:
        """ Cut the old tool results down, then leave the oldest messages out, until under TARGET: how many of each """
        target: float = self.__size * TARGET
        results: int = 0
        while self.__count(used) > target and self.__stubbed < last:
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
        while self.__count(used) > target and self.__hidden < last:
            end: int = next(i for i in range(self.__hidden + 1, last + 1) if history[i]["role"] != "tool")
            for i in range(self.__hidden, end):
                if messages[i] is not None and i != request and history[i]["role"] != "system":
                    used -= size_of(messages[i])
                    messages[i] = None
                    dropped += 1
            self.__hidden = end
        return results, dropped

    def __extra(self) -> int:
        """ The characters the summary adds, with the question it answers """
        return sum(size_of(message) for message in self.__recalled()) if self.__summary else 0

    def __recalled(self) -> list[dict]:
        """
            The summary, as an exchange right after the system prompt: the user asks what was said, the model answers
            with it. A model trusts what it said itself far more than the end of a long system prompt (it read the
            files again)
        """
        return [{"role": "user", "content": SUMMARY_ASKED},
                {"role": "assistant", "content": SUMMARY_TITLE + self.__summary}]

    def __sum_up(self, history: list[dict], request: int) -> bool:
        """ The messages left out since the last summary, summed up with it: whether a summary was made """
        if self.__summarize is None or self.__hidden <= self.__summed:
            return False
        left: list[dict] = [history[i] for i in range(self.__summed, min(self.__hidden, len(history)))
                            if history[i]["role"] != "system" and i != request]
        # Never asked twice for the same messages, even if the model failed: they are then only left out
        self.__summed = self.__hidden
        summary: str | None = self.__summarize(self.__summary, left) if left else None
        if not summary:
            return False
        self.__summary = summary
        return True

    def __with_summary(self, shown: list[dict]) -> list[dict]:
        """ The summary of what was left out, after the system prompt """
        if not self.__summary:
            return shown
        start: int = 1 if shown and shown[0]["role"] == "system" else 0
        return [*shown[:start], *self.__recalled(), *shown[start:]]

    def __shown(self, message: dict, index: int, request: int) -> dict | None:
        """ A message as the model sees it now: left out, cut down, or whole """
        if message["role"] != "system" and index != request and 1 <= index < self.__hidden:
            return None
        if message["role"] == "tool" and index < self.__stubbed and len(message["content"]) >= STUB_MIN_CHARS:
            return {**message, "content": stub(message["content"])}
        return message
