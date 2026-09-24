##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## App Class (the manager)
##

from interface.interface import Interface
from interface.cli import CLI
from model.model import OllamaModel
from model.reply import Reply

class App:
    """ App Class """
    def __init__(self, settings: dict[str], system_prompt: str):
        """ Init the Application class """
        self.__settings: dict[str] = settings

        # NOTE: Raisable
        self.__model : OllamaModel = OllamaModel(settings["chat.uri"], f"{settings["chat.model.name"]}:{settings["chat.model.parameters"]}")

        self.__stream: Interface   = CLI("> ")

        self.__history: list[dict] = [{
            "role": "system",
            "content": system_prompt
        }]

    @property
    def stream(self) -> Interface:
        """ Get the current stream (interface) """
        return self.__stream

    def run(self):
        """ Run the application """

        while True:
            try:
                u = self.stream.getUserInput()

                self.__history.append(
                    {
                        "role": "user",
                        "content": u
                    }
                )

                self.stream.out("\n", end="")

                reply: Reply = self.__model.chat(self.__history, on_text=self.__print_chunck)

                self.stream.out("\n")

                self.__history.append(
                    {
                        "role": "assistant",
                        "content": reply.content
                    }
                )

            except KeyboardInterrupt:
                self.stream.debug("User has closed the session...\n")
                break
        return 0

    def __print_chunck(self, text) -> None:
        """ Print a chunck """
        self.stream.out(text, end="", flush=True)
