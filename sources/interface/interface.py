##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## CLI Interface
##

class Interface:
    def __init__(self) -> None:
        self.__prompt   : str = "> "
        self.__callBacks: dict[str, "function"] = {
            "onRead": None,
            "onDrain": None,
        }
        self.__running  : bool           = True

    def get(self) -> str | None:
        """ Receive a message by asking a prompt """
        ...

    def out(self, response: str) -> None:
        """ Show the user a response """
        # if response is not None and self.__callBacks["onDrain"]:
        #     self.__callBacks["onDrain"](response)
        ...

    def setCallback(self, evt: str, func: "function") -> None:
        """ Set a callback """
        if evt not in self.__callBacks.keys():
            raise KeyError(f"Callbacks catalog does not have a {evt} event")
        self.__callBacks[evt] = func

    # def run(self) -> None:
    #     """ Run the interface """
    #     while self.__running:
    #         uinp: str | None = self.receive(self.__prompt)
    #         if self.__callBacks["onRead"]:
    #             resp = self.__callBacks["onRead"](uinp)
    #             self.show(resp)
    #             if self.__callBacks["onDrain"]:
    #                 self.__callBacks["onDrain"](resp)


    @property
    def prompt(self) -> str:
        """ Get the prompt """
        return self.__prompt

    @prompt.setter
    def prompt(self, prompt: str) -> None:
        """ Set the prompt """
        if prompt and isinstance(prompt, str):
            self.__prompt = prompt

class CLI(Interface):
    def __init__(self, prompt: str | None = None) -> None:
        super().__init__()
        if prompt:
            self.prompt = prompt

    def get(self) -> str:
        """ Get a message from terminal """
        message = input(self.prompt)
        return message

    def out(self, response: str, *, end: str ="", flush: bool = False) -> None:
        """ Show smth in the CLI """
        print(response, end=end, flush=flush)
