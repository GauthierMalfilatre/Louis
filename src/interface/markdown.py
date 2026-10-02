##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Markdown styling of the replies, as they stream
##
import re
import unicodedata

# The flags a piece of text can have, combined in its style (a frozenset): each interface lays them out its own way
#   inline : bold, italic, strike, code, link, url
#   a line : title (with h1 to h6), quote, bullet (a list mark), mark (the bar of a quote), rule (---)
#   blocks : block (a line of a code block), lang (its language), header and border (of a table)
Style = frozenset[str]

TEXT: Style = frozenset()

# What begins a line, matched on the line read so far
FENCE   : re.Pattern = re.compile(r"( *)(`{3,}|~{3,})[ \t]*([\w+#.-]*)[ \t]*$")
RULE    : re.Pattern = re.compile(r" {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
HEADING : re.Pattern = re.compile(r" {0,3}(#{1,6})[ \t]+")
QUOTE   : re.Pattern = re.compile(r" {0,3}>[ \t]?")
BULLET  : re.Pattern = re.compile(r"( *)[-*+][ \t]+")
NUMBER  : re.Pattern = re.compile(r"( *)(\d{1,9}[.)])[ \t]+")
TASK    : re.Pattern = re.compile(r"\[([ xX])\][ \t]+")
# A line still too short to tell what begins it: it waits for more
UNDECIDED: re.Pattern = re.compile(r" *(?:`+[\w+#.-]*|~+[\w+#.-]*|[-*_][-*_ \t]*|#{1,6}|\d{1,9}[.)]?|>|[-*+][ \t]+\[[ xX]?\]?)?")

# Links, whole or not finished yet
LINK         : re.Pattern = re.compile(r"\[([^\]\n]+)\]\(([^)\s]*)\)")
LINK_BEGUN   : re.Pattern = re.compile(r"\[[^\]\n]*(?:\](?:\([^)\s]*)?)?")
AUTOLINK     : re.Pattern = re.compile(r"<(https?://[^>\s]+)>")
AUTOLINK_BEGUN: re.Pattern = re.compile(r"<(?:h(?:t(?:t(?:p(?:s?(?::(?:/(?:/[^>\s]*)?)?)?)?)?)?)?)?")
LINK_WAIT    : int = 300    # Longer than this, a [ or a < is not a link: it goes as it is

TABLE_SEPARATOR: re.Pattern = re.compile(r" *\|? *:?-+:? *(?:\| *:?-+:? *)*\|? *$")
SEPARATOR_BEGUN: re.Pattern = re.compile(r" *\|? *:?-*:? *(?:\| *:?-*:? *)*\|? *")
PIPE           : re.Pattern = re.compile(r"(?<!\\)\|")

# A piece that is no text: the line shown last must be taken back (it was the header of a table, now drawn whole)
RETRACT: Style = frozenset({"retract"})

def kind(char: str) -> str:
    """ What a character is for the rules of * and _: a space, a punctuation (or a symbol), or else """
    if char.isspace():
        return "space"
    return "punctuation" if unicodedata.category(char)[0] in "PS" else "other"

def wrap(pieces: list[tuple[str, Style]], width: int) -> list[list[tuple[str, Style]]]:
    """ Styled pieces cut into lines of width at most, between their words (a word too long is cut in it) """
    lines: list[list[tuple[str, Style]]] = [[]]
    used: int = 0
    for text, style in pieces:
        for token in re.findall(r"\S+|\s+", text):
            if token.isspace():
                # One space, between two words of a line only
                if used and used < width:
                    lines[-1].append((" ", style))
                    used += 1
                continue
            if used and used + len(token) > width:
                if lines[-1][-1][0] == " ":
                    lines[-1].pop()
                lines.append([])
                used = 0
            while used + len(token) > width:
                lines[-1].append((token[:width], style))
                lines.append([])
                token = token[width:]
            lines[-1].append((token, style))
            used += len(token)
    if lines[-1] and lines[-1][-1][0] == " ":
        lines[-1].pop()
    return lines

def fit(widths: list[int], room: int) -> list[int]:
    """ The widths of columns narrowed, the widest first, for their text to hold in room: as they are if it can not """
    widths = list(widths)
    while sum(widths) > room:
        widest: int = max(range(len(widths)), key=lambda n: widths[n])
        # Narrower than a short word, a column is no use: the table overflows instead
        if widths[widest] <= 6:
            return widths
        widths[widest] -= 1
    return widths

def cells(line: str) -> list[str]:
    """ The cells of a line of a table, without its outer bars """
    line = line.strip()
    line = line[1:] if line.startswith("|") else line
    line = line[:-1] if line.endswith("|") and not line.endswith("\\|") else line
    return [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", line)]

class Markdown:
    """
        Styles the Markdown the model writes, piece by piece as it streams. Gives (text, style) pieces without
        their marks, style being a frozenset of flags (see Style). What can not be told yet (a mark cut between
        two pieces, the start of a line, a link, a table) waits for the next piece: flush() lets it go at the end.
        A table is drawn once whole, with its columns aligned. Its header may have been shown as a line already
        (a line with a bar is a header only once a rule comes under it): a RETRACT piece then asks the interface
        to take back the line it showed last. Bold, italic and so on end with their line. With a width, a table
        wider has its widest columns narrowed, their cells on several lines
    """
    def __init__(self, width: int | None = None):
        """ Init the styling, at the start of a line: the tables fit in width columns, if given """
        self.width       : int | None = width
        self.__pending   : str        = ""
        self.__line_start: bool       = True
        # The fence of the code block the text is in ("```", "~~~~"...), None outside of one
        self.__fence     : str | None = None
        # The lines of the table being read
        self.__table     : list[str]  = []
        # The style of the whole line (a title, a quote), and the one opened in it (bold, italic, strike)
        self.__line      : Style      = TEXT
        self.__inline    : set[str]   = set()
        # The number of backticks of the code span open, 0 outside of one
        self.__code      : int        = 0
        # The character read last, for the rules of * and _
        self.__previous  : str        = "\n"
        # The line being read as it was written, and the one before it: a table header, if a rule comes under it
        self.__raw       : str        = ""
        self.__last_line : str        = ""

    def feed(self, text: str) -> list[tuple[str, Style]]:
        """ Style a piece of the reply: what can not be told yet waits for the next one """
        return self.__parse(self.__pending + text, final=False)

    def flush(self) -> list[tuple[str, Style]]:
        """ The end of the reply: what was waiting goes, the table left is drawn, and the styles are reset """
        pieces: list[tuple[str, Style]] = self.__parse(self.__pending, final=True)
        pieces += self.__end_table()
        self.__init__(self.width)
        return pieces

    def __parse(self, buffer: str, *, final: bool) -> list[tuple[str, Style]]:
        """ Style buffer, keeping back its end when it can not be told yet """
        pieces: list[tuple[str, Style]] = []
        self.__pending = ""
        i: int = 0
        while i < len(buffer):
            if self.__line_start:
                end: int = buffer.find("\n", i)
                line: str = buffer[i:] if end == -1 else buffer[i:end]
                whole: bool = end != -1 or final
                after: int = len(buffer) if end == -1 else end + 1
                piped: bool = self.__fence is None and PIPE.search(line) is not None
                # A rule (--- | ---) under a line with a bar: that line, already shown, was the header of a table.
                # Kept back while it may be one, even before its first bar (":---", "---")
                if self.__fence is None and not self.__table and PIPE.search(self.__last_line):
                    if not whole and SEPARATOR_BEGUN.fullmatch(line):
                        self.__pending = buffer[i:]
                        break
                    if whole and piped and TABLE_SEPARATOR.match(line):
                        pieces.append(("", RETRACT))
                        self.__table = [self.__last_line, line]
                        self.__last_line = ""
                        i = after
                        continue
                # A table is kept until it ends, to align its columns: its lines start with a bar, or have one
                if piped and (self.__table or line.lstrip().startswith("|")):
                    if not whole:
                        self.__pending = buffer[i:]
                        break
                    self.__table.append(line)
                    self.__last_line = ""
                    i = after
                    continue
                # A table goes on while its lines have a bar: only a whole line tells
                if self.__table and not whole:
                    self.__pending = buffer[i:]
                    break
                pieces += self.__end_table()
                if not whole and UNDECIDED.fullmatch(line):
                    self.__pending = buffer[i:]
                    break
                consumed, over = self.__line_head(line, whole, pieces)
                if over:
                    self.__last_line = ""
                    i = after
                    continue
                self.__raw = line[:consumed]
                i += consumed
                self.__line_start = False
                continue
            char: str = buffer[i]
            if char == "\n":
                self.__add(pieces, "\n", frozenset({"block"}) if self.__fence is not None else TEXT)
                self.__line, self.__inline, self.__code = TEXT, set(), 0
                self.__line_start, self.__previous = True, "\n"
                self.__last_line, self.__raw = (self.__raw if self.__fence is None else ""), ""
                i += 1
                continue
            if self.__fence is not None:
                end = buffer.find("\n", i)
                code: str = buffer[i:] if end == -1 else buffer[i:end]
                self.__add(pieces, code, frozenset({"block"}))
                i += len(code)
                continue
            read: int | None = self.__inline_mark(buffer[i:], final, pieces)
            if read is None:
                self.__pending = buffer[i:]
                break
            self.__raw += buffer[i:i + read]
            i += read
        return pieces

    def __line_head(self, line: str, whole: bool, pieces: list[tuple[str, Style]]) -> tuple[int, bool]:
        """
            Read what begins a line: a fence, a rule, a quote, a title, a list item. Gives the characters read, and
            whether the whole line was (a fence or a rule are whole marks)
        """
        fence = FENCE.match(line) if whole else None
        if self.__fence is not None:
            # Only a fence as long, of the same character, and without a language closes a block
            if fence and fence[2][0] == self.__fence[0] and len(fence[2]) >= len(self.__fence) and not fence[3]:
                self.__fence = None
                return len(line), True
            return 0, False
        if fence:
            self.__fence = fence[2]
            if fence[3]:
                self.__add(pieces, fence[3] + "\n", frozenset({"lang"}))
            return len(line), True
        if whole and RULE.match(line):
            self.__add(pieces, "───\n", frozenset({"rule"}))
            return len(line), True
        read: int = 0
        line_style: set[str] = set()
        if quote := QUOTE.match(line):
            self.__add(pieces, "│ ", frozenset({"mark"}))
            line_style.add("quote")
            read = quote.end()
        rest: str = line[read:]
        if heading := HEADING.match(rest):
            line_style |= {"title", f"h{len(heading[1])}"}
            read += heading.end()
        elif bullet := BULLET.match(rest):
            read += bullet.end()
            if task := TASK.match(line[read:]):
                self.__add(pieces, f"{bullet[1]}{'☑' if task[1] in 'xX' else '☐'} ", frozenset({"bullet"}))
                read += task.end()
            else:
                self.__add(pieces, f"{bullet[1]}• ", frozenset({"bullet"}))
        elif number := NUMBER.match(rest):
            self.__add(pieces, f"{number[1]}{number[2]} ", frozenset({"bullet"}))
            read += number.end()
        self.__line = frozenset(line_style)
        return read, False

    def __inline_mark(self, rest: str, final: bool, pieces: list[tuple[str, Style]]) -> int | None:
        """ Read the next character of a line, or the mark it begins: the characters read, None to wait for more """
        char: str = rest[0]
        style: Style = self.__style()
        if self.__code:
            if char != "`":
                self.__add(pieces, char, style)
                return 1
            run: int = len(rest) - len(rest.lstrip("`"))
            if run == len(rest) and not final:
                return None
            if run == self.__code:
                self.__code = 0
            else:
                self.__add(pieces, rest[:run], style)
            self.__previous = "`"
            return run
        if char == "\\":
            if len(rest) == 1 and not final:
                return None
            if len(rest) > 1 and kind(rest[1]) == "punctuation":
                self.__add(pieces, rest[1], style)
                self.__previous = rest[1]
                return 2
        if char in "`*_~":
            run = len(rest) - len(rest.lstrip(char))
            # The character after the run tells whether it opens or closes: it must be known
            if run == len(rest) and not final:
                return None
            if char == "`":
                self.__code = run
            elif not self.__delimiter(char, run, rest[run] if run < len(rest) else "\n"):
                self.__add(pieces, rest[:run], style)
            self.__previous = char
            return run
        if char == "[":
            if link := LINK.match(rest):
                self.__add(pieces, link[1], style | {"link"})
                if link[2] and link[2] != link[1]:
                    self.__add(pieces, f" ({link[2]})", style | {"url"})
                self.__previous = ")"
                return link.end()
            if not final and len(rest) < LINK_WAIT and LINK_BEGUN.fullmatch(rest):
                return None
        if char == "<":
            if link := AUTOLINK.match(rest):
                self.__add(pieces, link[1], style | {"link"})
                self.__previous = ">"
                return link.end()
            if not final and len(rest) < LINK_WAIT and AUTOLINK_BEGUN.fullmatch(rest):
                return None
        self.__add(pieces, char, style)
        self.__previous = char
        return 1

    def __delimiter(self, char: str, run: int, after: str) -> bool:
        """
            A run of * or _ (italic, bold, both) or of ~~ (strike): opened or closed as CommonMark says it can be,
            by the characters around it. False if it does neither: it is then text
        """
        names: tuple[str, ...] | None = (
            {2: ("strike",)} if char == "~" else {1: ("italic",), 2: ("bold",), 3: ("bold", "italic")}
        ).get(run)
        if names is None:
            return False
        before: str = kind(self.__previous)
        next_: str = kind(after)
        left: bool = next_ != "space" and (next_ != "punctuation" or before in ("space", "punctuation"))
        right: bool = before != "space" and (before != "punctuation" or next_ in ("space", "punctuation"))
        # An _ inside a word (snake_case) neither opens nor closes
        opens: bool = left and (char != "_" or not right or before == "punctuation")
        closes: bool = right and (char != "_" or not left or next_ == "punctuation")
        if closes and all(name in self.__inline for name in names):
            self.__inline -= set(names)
            return True
        if opens and not any(name in self.__inline for name in names):
            self.__inline |= set(names)
            return True
        return False

    def __style(self) -> Style:
        """ The style of the text now: the one of its line, what is open in it, code """
        return self.__line | self.__inline | ({"code"} if self.__code else set())

    def __end_table(self) -> list[tuple[str, Style]]:
        """ The table read, with its columns aligned: its header bold, a rule under it, bars between the cells """
        if not self.__table:
            return []
        rows: list[list[str]] = [cells(line) for line in self.__table]
        header: bool = len(rows) > 1 and TABLE_SEPARATOR.match(self.__table[1]) is not None
        if header:
            del rows[1]
        self.__table = []
        # Each cell styled on its own, to know its width without its marks
        styled: list[list[list[tuple[str, Style]]]] = [
            [Markdown().__cell(cell) for cell in row] for row in rows
        ]
        columns: int = max(len(row) for row in styled)
        widths: list[int] = [
            max((sum(len(text) for text, _ in row[n]) for row in styled if n < len(row)), default=0)
            for n in range(columns)
        ]
        # A cell takes its width, a space on each side, and a bar between two
        if self.width is not None:
            widths = fit(widths, self.width - 3 * columns + 1)
        border: Style = frozenset({"border"})
        pieces: list[tuple[str, Style]] = []
        for number, row in enumerate(styled):
            lines: list[list[list[tuple[str, Style]]]] = [
                wrap(row[n] if n < len(row) else [], widths[n]) for n in range(columns)
            ]
            for height in range(max(len(cell) for cell in lines)):
                for n in range(columns):
                    part: list[tuple[str, Style]] = lines[n][height] if height < len(lines[n]) else []
                    self.__add(pieces, " ", TEXT)
                    for text, style in part:
                        self.__add(pieces, text, style | ({"header"} if header and number == 0 else set()))
                    self.__add(pieces, " " * (widths[n] - sum(len(text) for text, _ in part) + 1), TEXT)
                    if n < columns - 1:
                        self.__add(pieces, "│", border)
                self.__add(pieces, "\n", TEXT)
            if header and number == 0:
                self.__add(pieces, "┼".join("─" * (width + 2) for width in widths) + "\n", border)
        return pieces

    def __cell(self, text: str) -> list[tuple[str, Style]]:
        """ A cell of a table, styled as a line of its own """
        self.__line_start = False
        return [(piece, style) for piece, style in self.__parse(text, final=True) if piece != "\n"]

    @staticmethod
    def __add(pieces: list[tuple[str, Style]], text: str, style: Style) -> None:
        """ Add text to the last piece if it has the same style, else start a new one """
        if not text:
            return
        if pieces and pieces[-1][1] == style:
            pieces[-1] = (pieces[-1][0] + text, style)
        else:
            pieces.append((text, style))
