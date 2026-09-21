##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## CLI Interface
##
import os
import subprocess

class Interface:
    def __init__(self) -> None:
        self.__close: bool = False

    def get(self) -> str | None:
        ...

    def out(self, response: str) -> None:
        ...

    def isOpen(self) -> bool:
        return not self.__close

    def close(self) -> None:
        """ Close interface """
        self.__close = True

class CLI(Interface):
    def __init__(self, prompt: str = "> ") -> None:
        super().__init__()
        self.__prompt = prompt

    def get(self) -> str:
        """ Get a message from terminal """
        message = input(self.prompt)
        return message

    def out(self, response: str, *, end: str ="\n", flush: bool = False) -> None:
        """ Show smth in the CLI """
        print(response, end=end, flush=flush)

    def close(self) -> None:
        """ Close CLI """
        subprocess.run("clear")
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
