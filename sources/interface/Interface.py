##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## CLI Interface
##

class Interface:
    def __init__(self) -> None:
        self.__running  : bool           = True
        self.__callBacks: dict[str, "function"] = {
            "onRead": None,
            "onDrain": None,
        }
        self.__prompt   : str = "> "

    def receive(self, prompt) -> str | None:
        """ Receive a message by asking a prompt """
        ...

    def show(self, response: str) -> None:
        """ Show the user a response """
        if response is not None and self.__callBacks["onDrain"]:
            self.__callBacks["onDrain"](response)

    def setCallback(self, evt: str, func: "function") -> None:
        """ Set a callback """
        if evt not in self.__callBacks.keys():
            raise KeyError(f"Callbacks catalog does not have a {evt} event")
        self.__callBacks[evt] = func

    def run(self) -> None:
        """ Run the interface """
        while self.__running:
            uinp: str | None = self.receive(self.__prompt)
            if self.__callBacks["onRead"]:
                resp = self.__callBacks["onRead"](uinp)
                self.show(resp)
                if self.__callBacks["onDrain"]:
                    self.__callBacks["onDrain"](resp)

class CLI(Interface):
    def __init__(self) -> None:
        super().__init__()

    def receive(self, prompt) -> str:
        """ Get a message from terminal """
        message = input(prompt)
        return message

    def show(self, response: str) -> None:
        """ Show smth in the CLI """
