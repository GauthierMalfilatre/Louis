##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Markdown styling of the replies, as they stream
##
import re

HEADING: re.Pattern = re.compile(r"#{1,6} ")
FENCE  : str        = "```"

class Markdown:
    """
        Styles the Markdown the model writes, piece by piece as it streams: **bold**, `code`, ``` blocks and
        # titles. Gives (text, style) pieces without their marks, style being "text", "bold", "code", "block"
        or "title". A mark cut between two pieces waits for the next one: flush() lets it go at the end
    """
    def __init__(self):
        """ Init the styling, at the start of a line """
        self.__pending   : str  = ""
        self.__bold      : bool = False
        self.__code      : bool = False
        self.__block     : bool = False
        self.__title     : bool = False
        self.__line_start: bool = True

    def feed(self, text: str) -> list[tuple[str, str]]:
        """ Style a piece of the reply: what can not be known yet waits for the next one """
        return self.__parse(self.__pending + text, final=False)

    def flush(self) -> list[tuple[str, str]]:
        """ The end of the reply: what was waiting goes as it is, and the styles are reset """
        pieces: list[tuple[str, str]] = self.__parse(self.__pending, final=True)
        self.__init__()
        return pieces

    def __parse(self, buffer: str, *, final: bool) -> list[tuple[str, str]]:
        """ Style buffer, keeping back its end if it may be the beginning of a mark """
        pieces: list[tuple[str, str]] = []
        self.__pending = ""
        i: int = 0
        while i < len(buffer):
            rest: str = buffer[i:]
            if self.__line_start:
                # A fence opens or closes a block: its whole line is the mark (with its language). It may be
                # indented, in a list: the spaces of a line start wait to know whether a fence comes after them
                stripped: str = rest.lstrip(" ")
                if stripped.startswith(FENCE) or (not final and FENCE.startswith(stripped)):
                    end: int = rest.find("\n")
                    if end == -1 and not final:
                        self.__pending = rest
                        break
                    if stripped.startswith(FENCE):
                        self.__block = not self.__block
                        i += len(rest) if end == -1 else end + 1
                        continue
                if not self.__block:
                    if heading := HEADING.match(rest):
                        self.__title, self.__line_start = True, False
                        i += heading.end()
                        continue
                    if not final and re.fullmatch(r"#{1,6}", rest):
                        self.__pending = rest
                        break
            char: str = buffer[i]
            if char == "\n":
                self.__add(pieces, char, "block" if self.__block else "text")
                self.__title, self.__line_start = False, True
                i += 1
                continue
            self.__line_start = False
            if not self.__block:
                if char == "`":
                    self.__code = not self.__code
                    i += 1
                    continue
                if char == "*" and not self.__code:
                    if rest.startswith("**"):
                        self.__bold = not self.__bold
                        i += 2
                        continue
                    if rest == "*" and not final:
                        self.__pending = rest
                        break
            self.__add(pieces, char, self.__style())
            i += 1
        return pieces

    def __style(self) -> str:
        """ The style of the text now: a block, some code, a title, bold, or plain text """
        if self.__block:
            return "block"
        if self.__code:
            return "code"
        if self.__title:
            return "title"
        return "bold" if self.__bold else "text"

    @staticmethod
    def __add(pieces: list[tuple[str, str]], text: str, style: str) -> None:
        """ Add text to the last piece if it has the same style, else start a new one """
        if pieces and pieces[-1][1] == style:
            pieces[-1] = (pieces[-1][0] + text, style)
        else:
            pieces.append((text, style))
