##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## CLI Class that inherit from Interface
##
from interface.interface import Interface
import sys

class CLI(Interface):
    """ Class CLI to interact with the user in the terminal """
    def __init__(self, prompt: str = "> "):
        """ Init the CLI class """
        self.__prompt: str = prompt
        super().__init__()

    @property
    def promp(self) -> str:
        """ Get the prompt of the CLI """
        return self.__prompt

    def getUserInput(self):
        """ Get the user input from stdin """
        self.out(self.promp, end="", flush=True)
        uin: str = sys.stdin.readline()
        if not isinstance(uin, str):
            raise TypeError("User input doesnt seems to be an str")
        return uin

    def out(self, content, *, end="\n", flush=False):
        """ Print somthing on the stdout """
        sys.stdout.write(content + end)
        if flush:
            sys.stdout.flush()
        return self

    def debug(self, content):
        """ Print smth on stderr """
        sys.stderr.write(content)
        return self
