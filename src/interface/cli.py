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
    def __init__(self):
        """ Init the CLI class """
        super().__init__()

    def getUserInput(self):
        """ Get the user input from stdin """
        uin: str = sys.stdin.readline()
        if not isinstance(uin, str):
            raise TypeError("User input doesnt seems to be an str")
        return uin

    def out(self, content):
        """ Print somthing on the stdout """
        sys.stdout.write(content)
        return self

    def debug(self, content):
        """ Print smth on stderr """
        sys.stderr.write(content)
        return self
