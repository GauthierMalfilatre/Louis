##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## CLI in a curses window: the conversation above, the line being edited below
##
from interface.cli import CLI
from interface.markdown import Markdown, RETRACT
from events.event_bus import EventBus
from events.event import Event
from events.event_list import CHAT_TURN_STARTED, CHAT_TURN_ENDED, CHAT_CONTEXT, CHAT_THINKING, APP_STARTED
from events.event_list import SESSION_CREATED, SESSION_SAVED, SESSION_RESUMED, THINKING_ENABLED, THINKING_DISABLED
from events.event_list import REASONING_ENABLED, REASONING_DISABLED, EVAL_STARTED, EVAL_SCORED
import curses
import locale
import os
import random
import re
import sys
import threading
import time

PAD_LINES  : int   = 3000   # Lines of conversation kept: the oldest ones scroll away
# The words shown while Louis works, one at a time, another one drawn at random every BUSY_EVERY seconds
BUSY       : list[str] = ["Gamberging", "Gooning", "Phasing", "Zioning", "Larping", "Yapping", "Blablating", "Doomscrolling", "Asking my mom", "Taking coffee"]
BUSY_EVERY : float = 3.0
SPINNER    : str   = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
# The words of the status bar while the judge reads an answer again (eval/), changed as often as those of BUSY
JUDGING    : list[str] = ["Fact-checking", "Squinting", "Cross-examining", "Nitpicking", "Grading", "Sniffing sources",
                          "Double-checking", "Raising an eyebrow"]
# While the user types, the keys are waited for this long at most (ms): the judge's spinner turns in between
TICK       : int   = 100
BELOW      : int   = 2      # The lines below the conversation: the one being edited, and the status bar
FULL       : float = 0.8    # From this share of the context used on, its percentage is a warning
FOLD_LINES : int   = 15     # A diff, or a thinking, longer than this is folded
FOLD_KEEP  : int   = 12     # The lines of a folded diff still shown
WHEEL_LINES: int   = 3      # Lines scrolled by a notch of the mouse wheel

# Words and spaces of a text, to cut its lines between the words
TOKENS: re.Pattern = re.compile(r"\n|[^\S\n]+|\S+")

# The keys of the editor that are not keys of curses: a paste starting, Alt+Enter
PASTE    : int = -100
NEWLINE  : int = -101
WHEEL_UP  : int = curses.BUTTON4_PRESSED
WHEEL_DOWN: int = getattr(curses, "BUTTON5_PRESSED", 0)

# The colors of the web interface of the prototype, its dark theme (terminals mostly are): the closest
# ones of 256 colors, or of the 8 basic ones. name: (text, background), -1 is the one of the terminal
COLORS_256: dict[str, tuple[int, int]] = {
    "user"  : (231, 54),   # --user-text #f6f0ff on --user-bg #57219f, a bit darker
    "accent": (141, -1),   # --accent #bb8dff
    "ok"    : (78, -1),    # --ok #3ccf7a
    "danger": (211, -1),   # --danger #ff7aa2
    # The lines of a diff, as bands in Claude Code: dark green (#005f00) added, dark red (#5f0000) removed
    "added"  : (-1, 22),
    "removed": (-1, 52),
    "code"   : (-1, 236),  # --code-bg #221d2b, as a dark grey
}
COLORS_8: dict[str, tuple[int, int]] = {
    "user"  : (curses.COLOR_WHITE, curses.COLOR_MAGENTA),
    "accent": (curses.COLOR_MAGENTA, -1),
    "ok"    : (curses.COLOR_GREEN, -1),
    "danger": (curses.COLOR_RED, -1),
    "added"  : (curses.COLOR_BLACK, curses.COLOR_GREEN),
    "removed": (curses.COLOR_WHITE, curses.COLOR_RED),
    "code"   : (curses.COLOR_CYAN, -1),
}

# The keys some terminals send as escape sequences curses does not know (after the \x1b)
SEQUENCES: dict[str, int] = {
    "[A": curses.KEY_UP, "[B": curses.KEY_DOWN, "[C": curses.KEY_RIGHT, "[D": curses.KEY_LEFT,
    "OA": curses.KEY_UP, "OB": curses.KEY_DOWN, "OC": curses.KEY_RIGHT, "OD": curses.KEY_LEFT,
    "[H": curses.KEY_HOME, "[F": curses.KEY_END, "OH": curses.KEY_HOME, "OF": curses.KEY_END,
    "[1~": curses.KEY_HOME, "[4~": curses.KEY_END, "[3~": curses.KEY_DC,
    "[5~": curses.KEY_PPAGE, "[6~": curses.KEY_NPAGE,
    # Bracketed paste: the terminal marks what is pasted, so that its newlines do not send it
    "[200~": PASTE,
    "\r": NEWLINE, "\n": NEWLINE,
}

class CursesCLI(CLI):
    """
        The CLI, drawn in a curses window: the conversation scrolls above (PageUp, PageDown, the mouse wheel),
        the line is edited below, above a status bar. Everything it says comes from the CLI: the drawing, the
        reading, the Markdown and the thinking of the replies, the tool calls (completed in place when they
        end) and the folding of what is long are its own.
        The spinner below runs in a thread while Louis works: every drawing holds the lock
    """
    def __init__(self, prompt: str = "> "):
        """ Init the curses CLI, its window is opened by with """
        super().__init__(prompt)
        # What the conversation holds, to draw it again at another size: text, attribute, and the character
        # its lines are filled with up to the end ("" none, " " the bands of a diff or a code block, "─" a rule)
        self.__transcript: list[tuple[str, int, str]] = []
        self.__history   : list[str]                  = []
        # First line shown, None to follow the end of the conversation
        self.__top       : int | None                 = None
        self.__busy      : bool                       = False
        self.__asking    : bool                       = False
        self.__started   : float                      = 0.0
        # The word of BUSY shown while Louis works, and since when
        self.__busy_word : str                        = BUSY[0]
        self.__busy_since: float                      = 0.0
        # The tool call running: its row, the places of its bullet and of its end in the transcript, its bullet
        self.__tool      : tuple[int, int, int, str] | None = None
        # The attributes of the colors, by name: none when the terminal has no colors
        self.__colors    : dict[str, int]             = {}
        # The word written last (its row, its column, its text, its attribute), moved whole if it grows too long
        self.__word      : tuple[int, int, str, int] | None = None
        self.__full_line : bool                       = False
        self.__markdown  : Markdown                   = Markdown()
        # The rows where the lines of the reply start, by their place in the transcript: to take one back
        self.__line_rows : dict[int, int]             = {}
        # The thinking being shown (its place in the transcript, its row, its text), and the lines of a
        # folded diff (the place and the row of their notice, the lines)
        self.__thinking  : tuple[int, int, list[str]] | None = None
        self.__folded    : tuple[int, int, list[str]] | None = None
        # What the status bar shows: the user (a saved one or not), the session, the model, the thinking,
        # the context used (tokens, size, estimated), and a hint for a while (the commands Tab could complete)
        self.__user      : tuple[str, bool] | None    = None
        self.__session   : int | None                 = None
        self.__model     : str                        = ""
        self.__think     : bool                       = False
        self.__react     : bool                       = False
        self.__context  : tuple[int, int, bool] | None = None
        self.__hint      : str                        = ""
        self.__commands  : list[str]                  = []
        # Since when the judge reads an answer again (None: it does not), its word, since when, and whether the user is
        # typing: the bar is then drawn between the keys, by the thread that reads them
        self.__judging   : float | None               = None
        self.__judge_word: str                        = JUDGING[0]
        self.__judge_since: float                     = 0.0
        self.__judge_shown: bool                      = False
        self.__reading   : bool                       = False
        self.__lock      : threading.RLock            = threading.RLock()
        self.__stop      : threading.Event            = threading.Event()

    def __enter__(self) -> "CursesCLI":
        """ Open the window """
        locale.setlocale(locale.LC_ALL, "")
        # Otherwise curses waits a whole second after Escape, for the rest of a sequence
        os.environ.setdefault("ESCDELAY", "25")
        curses.initscr()
        curses.noecho()
        curses.cbreak()
        # Ctrl+C must not throw away what curses just drew: the screen would no longer be what it believes
        curses.noqiflush()
        self.__colors = CursesCLI.__palette()
        # The wheel scrolls the conversation (to select text with the mouse, hold Shift)
        curses.mousemask(WHEEL_UP | WHEEL_DOWN)
        curses.mouseinterval(0)
        sys.stdout.write("\x1b[?2004h")
        sys.stdout.flush()
        self.__layout()
        threading.Thread(target=self.__spin, daemon=True).start()
        return self

    def __exit__(self, *exception) -> None:
        """ Close the window: the terminal is as it was """
        self.__stop.set()
        with self.__lock:
            sys.stdout.write("\x1b[?2004l")
            sys.stdout.flush()
            curses.nocbreak()
            curses.echo()
            curses.endwin()

    def bind(self, bus: EventBus) -> "CursesCLI":
        """ Everything the CLI shows, the thinking of the model, the spinner below, and the status bar """
        super().bind(bus)
        bus.subscribe(self.__on_turn_started, CHAT_TURN_STARTED)
        bus.subscribe(self.__on_turn_ended, CHAT_TURN_ENDED)
        bus.subscribe(self.__on_thinking, CHAT_THINKING)
        bus.subscribe(self.__on_started, APP_STARTED)
        bus.subscribe(self.__on_session_created, SESSION_CREATED)
        bus.subscribe(lambda event: self.__set(session=event.data["id"]), SESSION_SAVED)
        bus.subscribe(lambda event: self.__set(session=event.data["id"]), SESSION_RESUMED)
        bus.subscribe(lambda event: self.__set(think=True), THINKING_ENABLED)
        bus.subscribe(lambda event: self.__set(think=False), THINKING_DISABLED)
        bus.subscribe(lambda event: self.__set(react=True), REASONING_ENABLED)
        bus.subscribe(lambda event: self.__set(react=False), REASONING_DISABLED)
        bus.subscribe(self.__on_context, CHAT_CONTEXT)
        bus.subscribe(self.__on_judging, EVAL_STARTED, EVAL_SCORED)
        return self

    # --- What the CLI shows ---------------------------------------------------------------------------

    def _write(self, text: str, *, dim: bool = False) -> None:
        """ Add text to the conversation, and show its end """
        with self.__lock:
            self.__add(text, curses.A_DIM if dim else curses.A_NORMAL)
            self.__follow()

    def _newline(self) -> None:
        """ Go to the next line, unless the conversation is at the start of one """
        with self.__lock:
            if self.__pad.getyx()[1] > 0:
                self.__add("\n", curses.A_NORMAL)

    def _on_text(self, event: Event) -> None:
        """ A piece of the reply, styled from its Markdown """
        with self.__lock:
            self.__end_thinking()
            self.__styled(self.__markdown.feed(event.data["text"]))
            self.__follow()

    def _on_reply(self, event: Event) -> None:
        """ The end of a reply: its last marks, the thinking folded if it was long, then a new line """
        with self.__lock:
            self.__styled(self.__markdown.flush())
            self.__end_thinking()
            super()._on_reply(event)
            self.__follow()

    def _on_reasoning_step(self, event: Event) -> None:
        """ A step of the reasoning loop: the thinking of the model (/think) ends before it, folded if it was long """
        with self.__lock:
            self.__end_thinking()
            super()._on_reasoning_step(event)
            self.__follow()

    def _on_reasoning_check(self, event: Event) -> None:
        """ The check of the draft, under it """
        with self.__lock:
            self.__end_thinking()
            super()._on_reasoning_check(event)
            self.__follow()

    def _on_tool_started(self, event: Event) -> None:
        """   ⠹ Lecture version.py : its bullet turns until the call ends """
        with self.__lock:
            self.__end_thinking()
            self._newline()
            bullet, label, detail = self._call_parts(event)
            detail = detail[:max(0, curses.COLS - 6 - len(label))]
            self.__add("  ", curses.A_NORMAL)
            bullet_index: int = len(self.__transcript)
            self.__add(bullet, self.__colors.get("accent", curses.A_BOLD))
            self.__add(f" {label}", curses.A_BOLD)
            if detail:
                self.__add(f" {detail}", curses.A_DIM)
            self.__add("\n", curses.A_NORMAL)
            # Read after writing: if the conversation scrolled, the line went up with it
            self.__tool = (self.__pad.getyx()[0] - 1, bullet_index, len(self.__transcript) - 1, bullet)
            self.__follow()

    def _on_tool_ended(self, event: Event) -> None:
        """
            The bullet green, or red if it could not be done, and what the call gave right below it:
              ● Lecture version.py
                ⎿ 1 ligne lue
        """
        with self.__lock:
            tool, self.__tool = self.__tool, None
            ok: bool = event.data["ok"]
            line_attr: int = curses.A_DIM if ok else self.__colors.get("danger", curses.A_BOLD)
            result: list[tuple[str, int, str]] = [
                ("    ⎿ ", curses.A_DIM, ""),
                (self._result_line(event)[:max(0, curses.COLS - 7)] + "\n", line_attr, ""),
            ]
            # Drawn again at another size, or a conversation so long that it scrolled: the row is lost
            if tool is None or self.__pad.getyx()[0] >= PAD_LINES - 2:
                self._newline()
                for text, attr, fill in result:
                    self.__add(text, attr, fill=fill)
                self.__follow()
                return
            row, bullet_index, end_index, bullet = tool
            color: int = self.__colors.get("ok" if ok else "danger", curses.A_BOLD)
            self.__transcript[bullet_index] = (bullet, color, "")
            y, x = self.__pad.getyx()
            self.__pad.addstr(row, 2, bullet, color)
            if end_index == len(self.__transcript) - 1:
                # Nothing written since the call: what it gave goes on below it
                self.__pad.move(y, x)
                for text, attr, fill in result:
                    self.__add(text, attr, fill=fill)
            else:
                # A permission was asked below the call: what it gave is slipped in right under it
                self.__transcript[end_index + 1:end_index + 1] = result
                self.__pad.move(row + 1, 0)
                self.__pad.insertln()
                for text, attr, _ in result:
                    self.__pad.addstr(text.rstrip("\n"), attr)
                self.__pad.move(y + 1, x)
                self.__word = None
            self.__follow()

    def _show_diff(self, preview: str) -> None:
        """ The diff, as in Claude Code: bands of green for the lines added, of red for the removed. Folded if long """
        with self.__lock:
            self._newline()
            lines: list[str] = preview.splitlines()
            folded: bool = len(lines) > FOLD_LINES
            for text, attr, fill in self.__diff(lines[:FOLD_KEEP] if folded else lines):
                self.__add(text, attr, fill=fill)
            if folded:
                self.__folded = (len(self.__transcript), self.__pad.getyx()[0], lines[FOLD_KEEP:])
                self.__add(f"  … {len(lines) - FOLD_KEEP} lignes de plus : v pour tout voir\n", curses.A_DIM)
            self.__follow()

    # --- What the user types --------------------------------------------------------------------------

    def _read_line(self, prompt: str) -> str:
        """
            Edit a line below: arrows, Home and End (Ctrl+A, Ctrl+E), Backspace and Delete, Ctrl+U to clear it,
            Up and Down for the history, Tab to complete a /command, Alt+Enter for a new line (a paste keeps its
            own), PageUp, PageDown and the wheel to scroll the conversation. "" on Ctrl+D
        """
        text, pos, index = "", 0, len(self.__history)
        self.__reading = True
        try:
            return self.__edit(prompt, text, pos, index)
        finally:
            self.__reading = False

    def __edit(self, prompt: str, text: str, pos: int, index: int) -> str:
        """ The loop of _read_line: the keys waited for a tick at most, for the judge's spinner to turn in between """
        redraw: bool = True
        while True:
            if redraw:
                with self.__lock:
                    self.__cursor(True)
                    self.__draw(prompt, text, pos)
            key = self.__key(tick=True)
            # A tick without a key changed nothing of the line: it is not drawn again
            redraw = key is not None
            if key is None:
                # No key in this tick: the bar of the judge goes on (and is drawn once more when it is done)
                with self.__lock:
                    if self.__judging is not None or self.__judge_shown:
                        self.__bar()
                        # The bar took the cursor: back where the user types
                        self.__input.refresh()
                continue
            if self.__hint:
                self.__set(hint="")
            if key in ("\n", "\r", curses.KEY_ENTER):
                break
            if key == "\x04":
                if not text:
                    self.__cursor(False)
                    return ""
                text = text[:pos] + text[pos + 1:]
            elif key in (curses.KEY_BACKSPACE, "\x7f", "\x08"):
                if pos:
                    text, pos = text[:pos - 1] + text[pos:], pos - 1
            elif key == curses.KEY_DC:
                text = text[:pos] + text[pos + 1:]
            elif key == curses.KEY_LEFT:
                pos = max(0, pos - 1)
            elif key == curses.KEY_RIGHT:
                pos = min(len(text), pos + 1)
            elif key in (curses.KEY_HOME, "\x01"):
                pos = 0
            elif key in (curses.KEY_END, "\x05"):
                pos = len(text)
            elif key == "\x15":
                text, pos = "", 0
            elif key in (curses.KEY_UP, curses.KEY_DOWN) and self.__history:
                index = max(0, index - 1) if key == curses.KEY_UP else min(len(self.__history), index + 1)
                text = self.__history[index] if index < len(self.__history) else ""
                pos = len(text)
            elif key in (PASTE, NEWLINE):
                added: str = self.__paste() if key == PASTE else "\n"
                text, pos = text[:pos] + added + text[pos:], pos + len(added)
            elif key == "\t" and prompt == self.promp:
                text, pos = self.__complete(text, pos)
            elif key in (curses.KEY_PPAGE, curses.KEY_NPAGE):
                self.__scroll(-1 if key == curses.KEY_PPAGE else 1)
            elif key == curses.KEY_MOUSE:
                self.__wheel()
            elif key == curses.KEY_RESIZE:
                with self.__lock:
                    self.__layout()
            elif isinstance(key, str) and key.isprintable():
                text, pos = text[:pos] + key + text[pos:], pos + 1
        with self.__lock:
            self.__cursor(False)
            if prompt == self.promp and text.strip():
                self.__history.append(text)
            # What the user typed stays in the conversation, as in a terminal: a message on the purple of the web
            if prompt == self.promp:
                bubble: int = self.__colors.get("user", curses.A_NORMAL) | curses.A_BOLD
                for n, line in enumerate(text.split("\n")):
                    self.__add(f" {prompt if n == 0 else ' ' * len(prompt)}{line} ", bubble)
                    self.__add("\n", curses.A_NORMAL)
            else:
                self.__add(prompt + text + "\n", curses.A_BOLD)
            self.__follow()
            self.__status()
        return text + "\n"

    def _choose(self, question: str, choices: str) -> str:
        """ A single key among choices (o for y, Enter for n), and v to unfold the diff above """
        labels: dict[str, str] = {"y": "oui", "n": "non", "a": "toujours"}
        self.__asking = True
        try:
            while True:
                shown: str = question + ("[v] tout voir  " if self.__folded else "")
                with self.__lock:
                    self.__cursor(True)
                    self.__input.erase()
                    self.__input.addnstr(0, 0, shown, curses.COLS - 1, curses.A_BOLD)
                    self.__input.refresh()
                key = self.__key()
                if isinstance(key, str):
                    key = "y" if key.lower() == "o" else key.lower()
                if key in ("\n", "\r", "\x04", curses.KEY_ENTER):
                    choice: str = "n"
                    break
                if key == "v" and self.__folded:
                    with self.__lock:
                        self.__unfold()
                elif key in (curses.KEY_PPAGE, curses.KEY_NPAGE):
                    self.__scroll(-1 if key == curses.KEY_PPAGE else 1)
                elif key == curses.KEY_MOUSE:
                    self.__wheel()
                elif key == curses.KEY_RESIZE:
                    with self.__lock:
                        self.__layout()
                elif isinstance(key, str) and key in choices:
                    choice = key
                    break
        finally:
            self.__asking = False
            self.__folded = None
        with self.__lock:
            self.__cursor(False)
            self.__add(f"{question.split('[')[0]}{labels.get(choice, choice)}\n", curses.A_BOLD)
            self.__follow()
            self.__status()
        return choice

    # --- The events of the curses CLI -----------------------------------------------------------------

    def __on_turn_started(self, event: Event) -> None:
        """ Louis works: the spinner below, and the Markdown of a new reply """
        with self.__lock:
            self.__markdown = Markdown(curses.COLS - 1)
            self.__line_rows.clear()
            self.__started = time.monotonic()
            self.__next_word()
            self.__busy = True
            self.__status()

    def __on_turn_ended(self, event: Event) -> None:
        """ Louis waits for a message again """
        with self.__lock:
            self.__end_thinking()
            self.__busy = False
            self.__status()

    def __on_judging(self, event: Event) -> None:
        """
            The judge starts or ends an answer. From its thread: nothing is drawn here, the thread reading the keys or
            the spinner's draw the bar (two threads in curses at once garble the screen)
        """
        with self.__lock:
            if event.name == EVAL_STARTED:
                self.__judging = time.monotonic()
                self.__judge_word, self.__judge_since = random.choice(JUDGING), self.__judging
            else:
                self.__judging = None

    def __on_thinking(self, event: Event) -> None:
        """ What the model thinks, dim, as it thinks it: folded once it replies if it was long """
        with self.__lock:
            if self.__thinking is None:
                self._newline()
                self.__thinking = (len(self.__transcript), self.__pad.getyx()[0], [])
                self.__add("✻ ", self.__colors.get("accent", curses.A_DIM))
            self.__thinking[2].append(event.data["text"])
            self.__add(event.data["text"], curses.A_DIM | getattr(curses, "A_ITALIC", 0))
            self.__follow()

    def __on_started(self, event: Event) -> None:
        """ The model and the commands, for the status bar and for Tab """
        self.__commands = [command["name"] for command in event.data["commands"]]
        self.__set(model=event.data["model"], think=event.data["think"], react=event.data.get("react", False))

    def __on_session_created(self, event: Event) -> None:
        """ The user, in the status bar: saved or not. The new session has no number before its first message """
        self.__set(user=(event.data["user"], event.data["persistent"]), session=None)

    def __on_context(self, event: Event) -> None:
        """ How full the context is, in the status bar """
        self.__set(context=(event.data["used"], event.data["size"], event.data["estimated"]))

    # --- Drawing --------------------------------------------------------------------------------------

    def __layout(self) -> None:
        """ Make the windows at the size of the terminal, and draw the conversation again in them """
        curses.update_lines_cols()
        self.__pad = curses.newpad(PAD_LINES, curses.COLS)
        self.__pad.scrollok(True)
        self.__input = curses.newwin(1, curses.COLS, curses.LINES - BELOW, 0)
        self.__input.keypad(True)
        self.__status_bar = curses.newwin(1, curses.COLS, curses.LINES - 1, 0)
        # Their rows changed with the width: the running tool gets its status below, nothing is folded again
        self.__tool, self.__thinking, self.__folded, self.__word = None, None, None, None
        self.__line_rows.clear()
        # The tables to come fit the new width: the ones drawn stay as they are
        self.__markdown.width = curses.COLS - 1
        for text, attr, fill in self.__transcript:
            self.__add(text, attr, remember=False, fill=fill)
        self.__refresh()
        self.__status()
        self.__bar()

    def __add(self, text: str, attr: int, *, remember: bool = True, fill: str = "") -> None:
        """
            Write in the conversation, without showing it yet, its lines cut between the words. With fill, its lines
            are filled up to their end with that character, in its attribute. Filled when drawn, not kept filled: it
            fits the window at any size
        """
        if remember:
            self.__transcript.append((text, attr, fill))
        try:
            if fill and fill != " ":
                # Drawn up to the end of each line (a rule): curses only fills a background with a byte
                lines: list[str] = text.split("\n")
                for n, line in enumerate(lines):
                    self.__pad.addstr(line, attr)
                    if n < len(lines) - 1:
                        self.__pad.addstr(fill * max(0, curses.COLS - 1 - self.__pad.getyx()[1]), attr)
                        self.__pad.addstr("\n")
                self.__word, self.__full_line = None, False
                return
            if fill:
                # curses clears the end of a line on a newline, with the background of the pad: a band
                self.__pad.bkgdset(fill, attr)
            for token in TOKENS.findall(text):
                if token != "\n" and token.isspace() and self.__word is None and self.__pad.getyx()[1] == 0 \
                        and self.__full_line:
                    # A word filled the line above to its very end: the space after it would start this one
                    self.__full_line = False
                    continue
                self.__full_line = False
                if token == "\n" or token.isspace():
                    self.__word = None
                    self.__pad.addstr(token, attr)
                else:
                    self.__put_word(token, attr)
        except curses.error:
            # Raised on the very last cell: the text is written all the same
            pass
        finally:
            if fill == " ":
                self.__pad.bkgdset(" ", curses.A_NORMAL)

    def __put_word(self, piece: str, attr: int) -> None:
        """ Write a word, or the next piece of the one written last: moved whole to the next line if it no longer fits """
        y, x = self.__pad.getyx()
        word: str = piece
        start_y, start_x = y, x
        if self.__word is not None:
            last_y, last_x, last, last_attr = self.__word
            # Right after the word written last, in the same style: the same word going on
            if last_attr == attr and (last_y, last_x + len(last)) == (y, x) and last_x + len(last) < curses.COLS:
                start_y, start_x, word = last_y, last_x, last + piece
        if start_x > 0 and start_x + len(word) > curses.COLS:
            self.__pad.move(start_y, start_x)
            self.__pad.clrtoeol()
            self.__pad.addstr("\n")
            start_y, start_x = self.__pad.getyx()
            self.__pad.addstr(word, attr)
        else:
            self.__pad.addstr(piece, attr)
        self.__word = (start_y, start_x, word, attr) if start_x + len(word) < curses.COLS else None
        self.__full_line = start_x + len(word) == curses.COLS

    def __styled(self, pieces: list[tuple[str, frozenset[str]]]) -> None:
        """
            Write pieces of a reply with the attributes of their Markdown style, a line after the other: each one
            starts a place of its own in the transcript, with its row kept, so that it can be taken back
        """
        for text, style in pieces:
            if style == RETRACT:
                self.__retract()
                continue
            attr, fill = self.__markdown_attr(style)
            for part in re.split(r"(?<=\n)", text):
                if not part:
                    continue
                if self.__pad.getyx()[1] == 0:
                    self.__line_rows[len(self.__transcript)] = self.__pad.getyx()[0]
                self.__add(part, attr, fill=fill)

    def __retract(self) -> None:
        """ Take back the line shown last: it was the header of a table, which is drawn whole now """
        start: int = len(self.__transcript) - 1
        if start < 0 or not self.__transcript[start][0].endswith("\n"):
            return
        while start > 0 and not self.__transcript[start - 1][0].endswith("\n"):
            start -= 1
        # Drawn again at another size since: its row is lost, it stays
        if start in self.__line_rows and self.__line_rows[start] <= self.__pad.getyx()[0]:
            self.__replace_tail(start, self.__line_rows[start], [])

    def __markdown_attr(self, style: frozenset[str]) -> tuple[int, str]:
        """
            The attribute of a Markdown style, and the character its lines are filled with: the flags add up, but a
            piece has one color (code first, then the accent of titles, links and list marks)
        """
        attr: int = curses.A_NORMAL
        if style & {"bold", "title", "header"}:
            attr |= curses.A_BOLD
        if style & {"italic", "quote"}:
            attr |= getattr(curses, "A_ITALIC", 0)
        if style & {"strike", "url", "lang", "border", "rule"}:
            attr |= curses.A_DIM
        if "link" in style:
            attr |= curses.A_UNDERLINE
        if style & {"code", "block"}:
            attr |= self.__colors.get("code", curses.A_REVERSE)
        elif style & {"title", "link", "bullet", "mark"}:
            attr |= self.__colors.get("accent", curses.A_NORMAL)
        fill: str = " " if "block" in style else "─" if "rule" in style else ""
        return attr, fill

    def __diff(self, lines: list[str]) -> list[tuple[str, int, str]]:
        """ The lines of a diff with their attributes: added and removed ones filled as bands """
        pieces: list[tuple[str, int, str]] = []
        for line in lines:
            if line.startswith("+"):
                pieces.append((line + "\n", self.__colors.get("added", curses.A_BOLD), " "))
            elif line.startswith("-"):
                pieces.append((line + "\n", self.__colors.get("removed", curses.A_DIM), " "))
            elif line.startswith("@@"):
                pieces.append((line + "\n", self.__colors.get("accent", curses.A_DIM), ""))
            else:
                pieces.append((line + "\n", curses.A_NORMAL, ""))
        return pieces

    def __replace_tail(self, index: int, row: int, pieces: list[tuple[str, int, str]]) -> None:
        """ Draw pieces instead of the end of the conversation, from its place index in the transcript, at row """
        # So long that it scrolled: the row is lost, the end stays as it is
        if self.__pad.getyx()[0] >= PAD_LINES - 1:
            return
        self.__pad.move(row, 0)
        self.__pad.clrtobot()
        del self.__transcript[index:]
        self.__line_rows = {place: kept for place, kept in self.__line_rows.items() if place < index}
        self.__word = None
        for text, attr, fill in pieces:
            self.__add(text, attr, fill=fill)
        self.__follow()

    def __unfold(self) -> None:
        """ The whole diff, in place of the notice of its folded lines """
        index, row, lines = self.__folded
        self.__folded = None
        self.__replace_tail(index, row, self.__diff(lines))

    def __end_thinking(self) -> None:
        """ The model replies: its thinking ends, folded to its beginning if it was long """
        if self.__thinking is None:
            return
        index, row, pieces = self.__thinking
        self.__thinking = None
        if self.__pad.getyx()[0] - row < FOLD_LINES:
            # Short, it stays: a blank line sets it apart from what follows
            self._newline()
            self.__add("\n", curses.A_NORMAL)
            return
        text: str = " ".join("".join(pieces).split())
        kept: str = text[:3 * curses.COLS].rsplit(" ", 1)[0]
        self.__replace_tail(index, row, [
            ("✻ ", self.__colors.get("accent", curses.A_DIM), ""),
            (f"{kept} …\n", curses.A_DIM | getattr(curses, "A_ITALIC", 0), ""),
            ("  (la suite de la réflexion est dans louis.log)\n", curses.A_DIM, ""),
        ])

    def __follow(self) -> None:
        """ Show the end of the conversation, where it goes on """
        self.__top = None
        self.__refresh()

    def __refresh(self) -> None:
        """ Show the conversation: its end, or the part scrolled to """
        height: int = curses.LINES - BELOW
        bottom: int = max(0, self.__pad.getyx()[0] - height + 1)
        top: int = bottom if self.__top is None else min(self.__top, bottom)
        self.__pad.refresh(top, 0, 0, 0, height - 1, curses.COLS - 1)

    def __scroll(self, direction: int, lines: int | None = None) -> None:
        """ Up (-1) or down (1), half a screen or some lines: back at the end, the conversation is followed again """
        with self.__lock:
            height: int = curses.LINES - BELOW
            bottom: int = max(0, self.__pad.getyx()[0] - height + 1)
            step: int = lines if lines is not None else height // 2
            top: int = max(0, min(bottom, (bottom if self.__top is None else self.__top) + direction * step))
            self.__top = None if top >= bottom else top
            self.__refresh()

    def __draw(self, prompt: str, text: str, pos: int) -> None:
        """ The line being edited, moved sideways so that the cursor stays in sight: ↵ for its new lines """
        width: int = curses.COLS - 1
        line: str = (prompt + text).replace("\n", "↵").replace("\t", " ")
        cursor: int = len(prompt) + pos
        start: int = max(0, cursor - width + 1)
        self.__input.erase()
        self.__input.addstr(0, 0, line[start:start + width])
        self.__input.move(0, cursor - start)
        self.__input.refresh()

    def __status(self, frame: int = 0) -> None:
        """ The line below tells when Louis works, and for how long: there is nothing to type there then """
        self.__input.erase()
        if self.__busy:
            now: float = time.monotonic()
            if now - self.__busy_since >= BUSY_EVERY:
                self.__next_word()
            spent: int = int(now - self.__started)
            text: str = f"{self.__busy_word} {SPINNER[frame % len(SPINNER)]} {spent}s"
            self.__input.addnstr(0, 0, text, curses.COLS - 1, self.__colors.get("accent", curses.A_DIM))
        self.__input.refresh()

    def __next_word(self) -> None:
        """ Another word of BUSY than the one shown, unless it is the only one """
        others: list[str] = [word for word in BUSY if word != self.__busy_word] or BUSY
        self.__busy_word = random.choice(others)
        self.__busy_since = time.monotonic()

    def __spin(self) -> None:
        """
            The thread of the spinner: a frame every tenth of a second while Louis works, below and on the bullet
            of the tool call running. Not while he asks: the cursor must stay where the user types
        """
        frame: int = 0
        while not self.__stop.wait(0.1):
            with self.__lock:
                if self.__busy and not self.__asking and not self.__stop.is_set():
                    frame += 1
                    if self.__tool is not None:
                        y, x = self.__pad.getyx()
                        self.__pad.addstr(self.__tool[0], 2, SPINNER[frame % len(SPINNER)],
                                          self.__colors.get("accent", curses.A_BOLD))
                        self.__pad.move(y, x)
                        self.__refresh()
                    self.__status(frame)
                # The judge's bar, when nobody types (a turn, /eval waiting for it): the keys' thread draws it otherwise
                if (self.__judging is not None or self.__judge_shown) and not self.__reading and not self.__asking \
                        and not self.__stop.is_set():
                    self.__bar()

    def __set(self, **values) -> None:
        """ Change what the status bar shows, and draw it again """
        with self.__lock:
            for name, value in values.items():
                setattr(self, f"_CursesCLI__{name}", value)
            self.__bar()

    def __bar(self) -> None:
        """ ● eratz · #12 · qwen3:8b · ✻ réflexion, green for a saved user and red otherwise, then the step by step mode, and on the right: contexte 23% """
        self.__status_bar.erase()
        width: int = curses.COLS - 1
        right: str = ""
        right_attr: int = curses.A_DIM
        if self.__hint:
            right = self.__hint
        elif self.__context is not None:
            used, size, estimated = self.__context
            right = f"contexte {'~' if estimated else ''}{round(100 * used / size)}%"
            if used >= FULL * size:
                right_attr = self.__colors.get("danger", curses.A_BOLD)
        # The judge at work, before the context:  ⚖ Squinting ⠹ 42s · contexte 23%
        judge: str = ""
        self.__judge_shown = self.__judging is not None and not self.__hint
        if self.__judge_shown:
            now: float = time.monotonic()
            if now - self.__judge_since >= BUSY_EVERY:
                self.__judge_word = random.choice([word for word in JUDGING if word != self.__judge_word] or JUDGING)
                self.__judge_since = now
            judge = f"⚖ {self.__judge_word} {SPINNER[int(now * 10) % len(SPINNER)]} {int(now - self.__judging)}s"
            judge += " · " if right else ""
        if judge and len(judge) + len(right) < width - 4:
            self.__status_bar.addstr(0, width - len(right) - len(judge), judge, self.__colors.get("accent", curses.A_DIM))
        room: int = max(0, width - len(right) - len(judge) - 2)
        x: int = 1
        if self.__user is not None and room > 3:
            name, saved = self.__user
            self.__status_bar.addnstr(0, x, "●", 1, self.__colors.get("ok" if saved else "danger", curses.A_BOLD))
            details: str = name
            if saved:
                details += f" · #{self.__session}" if self.__session is not None else " · nouvelle session"
            if self.__model:
                details += f" · {self.__model}"
            self.__status_bar.addnstr(0, x + 2, details, max(0, room - x - 2), curses.A_DIM)
            x += 2 + len(details)
            if self.__think and x + 14 < room:
                self.__status_bar.addstr(0, x, " · ✻ réflexion", self.__colors.get("accent", curses.A_DIM))
                x += 14
            if self.__react and x + 14 < room:
                self.__status_bar.addstr(0, x, " · ⟳ pas à pas", self.__colors.get("accent", curses.A_DIM))
        if right and len(right) < width - 4:
            self.__status_bar.addstr(0, width - len(right), right, right_attr)
        self.__status_bar.refresh()

    # --- Reading --------------------------------------------------------------------------------------

    def __key(self, tick: bool = False) -> str | int | None:
        """
            The next key: curses reads most of them, the escape sequences it does not know are read here.
            With tick, None when no key came in TICK ms
        """
        self.__input.timeout(TICK if tick else -1)
        try:
            key = self.__input.get_wch()
        except curses.error:
            return None
        if key != "\x1b":
            return key
        # A lone Escape, or a sequence of an unknown key: nothing
        return SEQUENCES.get(self.__sequence())

    def __sequence(self) -> str:
        """ The rest of an escape sequence, read without waiting """
        sequence: str = ""
        self.__input.nodelay(True)
        try:
            # Up to "[1;5D" (Ctrl+Left) or "[200~" (a paste): read whole, so that no piece of it is typed as text
            while len(sequence) < 6:
                try:
                    char = self.__input.get_wch()
                except curses.error:
                    break
                if not isinstance(char, str):
                    break
                sequence += char
                if char == "~" or (char.isalpha() and len(sequence) > 1) or (char in "\r\n" and len(sequence) == 1):
                    break
        finally:
            self.__input.nodelay(False)
        return sequence

    def __paste(self) -> str:
        """ What the terminal pastes, up to its end mark: its newlines are kept, not sent """
        pasted: list[str] = []
        while True:
            char = self.__input.get_wch()
            if char == "\x1b":
                if self.__sequence() == "[201~":
                    return "".join(pasted)
            elif isinstance(char, str):
                pasted.append("\n" if char == "\r" else char)

    def __complete(self, text: str, pos: int) -> tuple[str, int]:
        """ Tab: the /command begun, completed up to what its possible ends share, shown below if they are many """
        if not text.startswith("/") or " " in text[:pos]:
            return text, pos
        matches: list[str] = sorted(name for name in self.__commands if name.startswith(text[1:pos]))
        if not matches:
            return text, pos
        common: str = os.path.commonprefix(matches) + (" " if len(matches) == 1 else "")
        if len(matches) > 1:
            self.__set(hint="  ".join(f"/{name}" for name in matches))
        return "/" + common + text[pos:], 1 + len(common)

    def __wheel(self) -> None:
        """ The mouse wheel: some lines up or down """
        try:
            state: int = curses.getmouse()[4]
        except curses.error:
            return
        if state & WHEEL_UP:
            self.__scroll(-1, WHEEL_LINES)
        elif WHEEL_DOWN and state & WHEEL_DOWN:
            self.__scroll(1, WHEEL_LINES)

    @staticmethod
    def __palette() -> dict[str, int]:
        """ The attributes of the colors of the web page, as close as the terminal can: none without colors """
        if not curses.has_colors():
            return {}
        curses.start_color()
        try:
            # -1 is then the text or the background of the terminal itself
            curses.use_default_colors()
        except curses.error:
            return {}
        colors: dict[str, tuple[int, int]] = COLORS_256 if curses.COLORS >= 256 else COLORS_8
        attributes: dict[str, int] = {}
        for number, (name, (text, background)) in enumerate(colors.items(), 1):
            curses.init_pair(number, text, background)
            attributes[name] = curses.color_pair(number)
        return attributes

    @staticmethod
    def __cursor(visible: bool) -> None:
        """ Show the cursor only where the user types """
        try:
            curses.curs_set(1 if visible else 0)
        except curses.error:
            pass
