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
from tool.tool_manager import ToolManager
from tool.tool import Tool
from tool.impl.file.tool_tree import TreeTool
from tool.impl.file.tool_cat import CatTool

class App:
    """ App Class """
    def __init__(self, settings: dict[str], system_prompt: str):
        """ Init the Application class """
        self.__settings: dict[str] = settings

        self.__toolManager: ToolManager = ToolManager()\
            .register(TreeTool())\
            .register(CatTool())\

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

                for _ in range(self.__settings.get("chat.tools.maxdepth", 8)):
                    reply: Reply = self.__model.chat(
                        self.__history,
                        self.__toolManager.all(),
                        on_text=self.__print_chunck
                    )

                    self.__history.append(
                        {
                            "role": "assistant",
                            "content": reply.content,
                            "tool_calls": [call.to_dict() for call in reply.tool_calls] if reply.tool_calls else None
                        }
                    )

                    if not reply.tool_calls:
                        break

                    for call in reply.tool_calls:
                        tool: Tool = self.__toolManager.get(call.name)
                        resp = tool.handle(self, **call.arguments)

                        self.__history.append(
                            {
                                "role": "tool",
                                "content": resp,
                                "tool_name": call.name
                            }
                        )

                else:
                    self.stream.debug(f"Stopped after {self.__settings.get("chat.tools.maxdepth", 8)} round of tool calls\n")

                self.stream.out("\n")

            except KeyboardInterrupt:
                self.stream.debug("User has closed the session...\n")
                break
        return 0

    def __print_chunck(self, text) -> None:
        """ Print a chunck """
        self.stream.out(text, end="", flush=True)
