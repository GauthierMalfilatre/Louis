##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## CLI in a curses window: the conversation above, the line being edited below
##
from interface.cli import CLI
from events.event_bus import EventBus
from events.event import Event
from events.event_list import CHAT_TURN_STARTED, CHAT_TURN_ENDED
import curses
import locale
import os

PAD_LINES: int = 3000   # Lines of conversation kept: the oldest ones scroll away
BUSY     : str = "Gamberging"

# The colors of the web interface of the prototype, its dark theme (terminals mostly are): the closest
# ones of 256 colors, or of the 8 basic ones. name: (text, background), -1 is the one of the terminal
COLORS_256: dict[str, tuple[int, int]] = {
    "user"  : (231, 54),   # --user-text #f6f0ff on --user-bg #57219f, a bit darker
    "accent": (141, -1),   # --accent #bb8dff
    "ok"    : (78, -1),    # --ok #3ccf7a
    "danger": (211, -1),   # --danger #ff7aa2
}
COLORS_8: dict[str, tuple[int, int]] = {
    "user"  : (curses.COLOR_WHITE, curses.COLOR_MAGENTA),
    "accent": (curses.COLOR_MAGENTA, -1),
    "ok"    : (curses.COLOR_GREEN, -1),
    "danger": (curses.COLOR_RED, -1),
}

# The keys some terminals send as escape sequences curses does not know (after the \x1b)
SEQUENCES: dict[str, int] = {
    "[A": curses.KEY_UP, "[B": curses.KEY_DOWN, "[C": curses.KEY_RIGHT, "[D": curses.KEY_LEFT,
    "OA": curses.KEY_UP, "OB": curses.KEY_DOWN, "OC": curses.KEY_RIGHT, "OD": curses.KEY_LEFT,
    "[H": curses.KEY_HOME, "[F": curses.KEY_END, "OH": curses.KEY_HOME, "OF": curses.KEY_END,
    "[1~": curses.KEY_HOME, "[4~": curses.KEY_END, "[3~": curses.KEY_DC,
    "[5~": curses.KEY_PPAGE, "[6~": curses.KEY_NPAGE,
}

class CursesCLI(CLI):
    """
        The CLI, drawn in a curses window: the conversation scrolls above (PageUp, PageDown), the line is
        edited below. Everything it shows comes from the CLI: only the drawing, the reading, and the tool
        calls (completed in place when they end) are its own
    """
    def __init__(self, prompt: str = "> "):
        """ Init the curses CLI, its window is opened by with """
        super().__init__(prompt)
        # What the conversation holds, to draw it again at another size
        self.__transcript: list[tuple[str, int]]      = []
        self.__history   : list[str]                  = []
        # First line shown, None to follow the end of the conversation
        self.__top       : int | None                 = None
        self.__busy      : bool                       = False
        # The tool call running: its row, its line, and its place in the transcript
        self.__tool      : tuple[int, str, int] | None = None
        # The attributes of the colors, by name: none when the terminal has no colors
        self.__colors    : dict[str, int]             = {}

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
        self.__layout()
        return self

    def __exit__(self, *exception) -> None:
        """ Close the window: the terminal is as it was """
        curses.nocbreak()
        curses.echo()
        curses.endwin()

    def bind(self, bus: EventBus) -> "CursesCLI":
        """ Everything the CLI shows, and the line below telling when Louis works """
        super().bind(bus)
        bus.subscribe(lambda event: self.__status(True), CHAT_TURN_STARTED)
        bus.subscribe(lambda event: self.__status(False), CHAT_TURN_ENDED)
        return self

    def _write(self, text: str, *, dim: bool = False) -> None:
        """ Add text to the conversation, and show its end """
        self.__add(text, curses.A_DIM if dim else curses.A_NORMAL)
        self.__top = None
        self.__refresh()

    def _read_line(self, prompt: str) -> str:
        """
            Edit a line below: arrows, Home and End (Ctrl+A, Ctrl+E), Backspace and Delete, Ctrl+U to clear it,
            Up and Down for the history, PageUp and PageDown to scroll the conversation. "" on Ctrl+D
        """
        text, pos, index = "", 0, len(self.__history)
        self.__cursor(True)
        while True:
            self.__draw(prompt, text, pos)
            key = self.__key()
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
            elif key in (curses.KEY_PPAGE, curses.KEY_NPAGE):
                self.__scroll(-1 if key == curses.KEY_PPAGE else 1)
            elif key == curses.KEY_RESIZE:
                self.__layout()
            elif isinstance(key, str) and key.isprintable():
                text, pos = text[:pos] + key + text[pos:], pos + 1
        self.__cursor(False)
        if prompt == self.promp and text.strip():
            self.__history.append(text)
        # What the user typed stays in the conversation, as in a terminal: a message on the purple of the web page
        if prompt == self.promp:
            self.__add(f" {prompt}{text} ", self.__colors.get("user", curses.A_NORMAL) | curses.A_BOLD)
            self.__add("\n", curses.A_NORMAL)
        else:
            self.__add(prompt + text + "\n", curses.A_BOLD)
        self.__top = None
        self.__refresh()
        self.__status(self.__busy)
        return text + "\n"

    def _on_tool_started(self, event: Event) -> None:
        """ The tool call, marked as running (…) until it ends """
        self._newline()
        line: str = self._tool_line(event)[:max(10, curses.COLS - 16)]
        self.out(f"{line} …", dim=True)
        # Read after writing: if the conversation scrolled, the line went up with it
        self.__tool = (self.__pad.getyx()[0] - 1, line, len(self.__transcript) - 1)

    def _on_tool_ended(self, event: Event) -> None:
        """ ✓ and the time it took, or ✗ and why: in place of the …, even if a permission was asked below it """
        tool, self.__tool = self.__tool, None
        # Drawn again at another size, or a conversation so long that it scrolled: the row is lost
        if tool is None or self.__pad.getyx()[0] >= PAD_LINES - 1:
            super()._on_tool_ended(event)
            return
        row, line, index = tool
        ok: bool = event.data["ok"]
        status: str = f"✓ {event.data['duration']:.2f}s" if ok else f"✗ {event.data['result'].splitlines()[0]}"
        status = status[:max(0, curses.COLS - 3 - len(line))]
        color: int = self.__colors.get("ok" if ok else "danger", curses.A_DIM)
        # The line of the call dim, its status in color: kept in pieces, to be drawn again the same way
        self.__transcript[index:index + 1] = [(f"{line}  ", curses.A_DIM), (status, color), ("\n", curses.A_NORMAL)]
        # Written over the line of the call, then back where the conversation goes on
        y, x = self.__pad.getyx()
        self.__pad.move(row, 0)
        self.__pad.clrtoeol()
        self.__pad.addstr(row, 0, f"{line}  ", curses.A_DIM)
        self.__pad.addstr(status, color)
        self.__pad.move(y, x)
        self.__refresh()

    def __key(self) -> str | int | None:
        """ The next key: curses reads most of them, the escape sequences it does not know are read here """
        key = self.__input.get_wch()
        if key != "\x1b":
            return key
        sequence: str = ""
        self.__input.nodelay(True)
        try:
            # Up to "[1;5D" (Ctrl+Left): read whole, so that no piece of it is typed as text
            while len(sequence) < 6:
                try:
                    char = self.__input.get_wch()
                except curses.error:
                    break
                if not isinstance(char, str):
                    break
                sequence += char
                if char == "~" or (char.isalpha() and len(sequence) > 1):
                    break
        finally:
            self.__input.nodelay(False)
        # A lone Escape, or a sequence of an unknown key: nothing
        return SEQUENCES.get(sequence)

    def __layout(self) -> None:
        """ Make the windows at the size of the terminal, and draw the conversation again in them """
        curses.update_lines_cols()
        self.__pad = curses.newpad(PAD_LINES, curses.COLS)
        self.__pad.scrollok(True)
        self.__input = curses.newwin(1, curses.COLS, curses.LINES - 1, 0)
        self.__input.keypad(True)
        # Its row changed with the width: the running tool will get its status below
        self.__tool = None
        for text, attr in self.__transcript:
            self.__add(text, attr, remember=False)
        self.__refresh()
        self.__status(self.__busy)

    def __add(self, text: str, attr: int, *, remember: bool = True) -> None:
        """ Write in the conversation, without showing it yet """
        if remember:
            self.__transcript.append((text, attr))
        try:
            self.__pad.addstr(text, attr)
        except curses.error:
            # Raised on the very last cell: the text is written all the same
            pass

    def __refresh(self) -> None:
        """ Show the conversation: its end, or the part scrolled to """
        height: int = curses.LINES - 1
        bottom: int = max(0, self.__pad.getyx()[0] - height + 1)
        top: int = bottom if self.__top is None else min(self.__top, bottom)
        self.__pad.refresh(top, 0, 0, 0, height - 1, curses.COLS - 1)

    def __scroll(self, direction: int) -> None:
        """ Half a screen up (-1) or down (1): back at the end, the conversation is followed again """
        height: int = curses.LINES - 1
        bottom: int = max(0, self.__pad.getyx()[0] - height + 1)
        top: int = max(0, min(bottom, (bottom if self.__top is None else self.__top) + direction * (height // 2)))
        self.__top = None if top >= bottom else top
        self.__refresh()

    def __draw(self, prompt: str, text: str, pos: int) -> None:
        """ The line being edited, moved sideways so that the cursor stays in sight """
        width: int = curses.COLS - 1
        line: str = prompt + text
        cursor: int = len(prompt) + pos
        start: int = max(0, cursor - width + 1)
        self.__input.erase()
        self.__input.addstr(0, 0, line[start:start + width])
        self.__input.move(0, cursor - start)
        self.__input.refresh()

    def __status(self, busy: bool) -> None:
        """ The line below tells when Louis works: there is nothing to type there then """
        self.__busy = busy
        self.__input.erase()
        if busy:
            self.__input.addnstr(0, 0, BUSY, curses.COLS - 1, self.__colors.get("accent", curses.A_DIM))
        self.__input.refresh()

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
