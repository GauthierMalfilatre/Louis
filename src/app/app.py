##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## App Class (the manager)
##

from interface.interface import Interface
from interface.cli import CLI
from model.model import OllamaModel

class App:
    """ App Class """
    def __init__(self, settings: dict[str]):
        """ Init the Application class """
        self.__settings: dict[str] = settings

        # NOTE: Raisable
        self.__model : OllamaModel = OllamaModel(settings["chat.uri"], f"{settings["chat.model.name"]}:{settings["chat.model.parameters"]}")

        self.__stream: Interface   = CLI()

    @property
    def stream(self) -> Interface:
        """ Get the current stream (interface) """
        return self.__stream

    def run(self):
        """ Run the application """
        while True:
            try:
                u = self.stream.getUserInput()

                self.stream.out(f"\n<- {u}")

            except KeyboardInterrupt:
                self.stream.debug("User has closed the session...\n")
                break
        return 0
