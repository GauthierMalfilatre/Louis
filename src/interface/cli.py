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
        # readline() gives "" only at the end of the input (Ctrl+D): an empty line is "\n"
        if not uin:
            raise EOFError
        return uin

    def ask(self, question: str) -> str:
        """ Ask the user a question on stdin, the answer is empty at the end of the input """
        self.out(question, end="", flush=True)
        return sys.stdin.readline()

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
