##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## CLI Interface
##
import curses
import os

class Interface:
    def __init__(self) -> None:
        self.__close  : bool = False
        self.__manager       = None

    def bind(self, manager) -> "Interface":
        """ Give access to the manager running this interface """
        self.__manager = manager
        return self

    @property
    def manager(self):
        """ Get the manager, None until bound """
        return self.__manager

    def get(self) -> str | None:
        ...

    def out(self, response: str, *, end, flush) -> None:
        ...

    def debug(self, response: str, *, end, flush) -> None:
        ...

    def isOpen(self) -> bool:
        return not self.__close

    def close(self) -> None:
        """ Close interface """
        self.__close = True

class CLI(Interface):
    PURPLE_256: int = 135

    def __init__(self, prompt: str = "> ") -> None:
        super().__init__()
        self.__prompt = prompt

        # self.__win = curses.initscr()
        # self.__ended: bool = False

        # curses.cbreak()
        # curses.start_color()
        # curses.use_default_colors()
        # purple = self.PURPLE_256 if curses.COLORS >= 256 else curses.COLOR_MAGENTA
        # curses.init_pair(1, purple, -1)
        # self.__win.keypad(True)
        # self.__win.scrollok(True)

    def get(self) -> str:
        """ Get a message from terminal """
        # self.__win.move(self.__win.getmaxyx()[0] - 3, 0)
        # self.__win.addstr(self.prompt, curses.color_pair(1))
        # self.__win.refresh()
        # curses.echo()
        # try:
        #     message = self.__win.getstr().decode("utf-8", errors="replace")
        # finally:
        #     curses.noecho()
        message = input(self.__prompt)
        return message

    def out(self, response: str, *, end: str ="\n", flush: bool = False) -> None:
        """ Show smth in the CLI """
        # if self.__ended:
            # refresh() after endwin() would re-enter curses mode and never leave it
        print(response, end=end, flush=True)
        return
        # self.__win.move(0, 0)
        # self.__win.addstr(response + end)
        # self.__win.refresh()

    def debug(self, response: str, *, end: str = "\n", flush: bool = False) -> None:
        print(response, end=end, flush=flush)

    def close(self) -> None:
        """ Close CLI """
        # if not self.__ended:
        #     self.__ended = True
        #     curses.endwin()
        super().close()

    @property
    def prompt(self) -> str:
        """ Get the prompt """
        return self.__prompt

    @prompt.setter
    def prompt(self, prompt: str) -> None:
        """ Set the prompt """
        if prompt and isinstance(prompt, str):
            self.__prompt = prompt
