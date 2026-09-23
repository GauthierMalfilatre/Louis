from tool.tools import Tool
import sys
import os

class WriteTool(Tool):
    def __init__(self):
        super().__init__("write_file", "Write a content in a file open as \"w+\"", {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Le chemin vers le fichier à construire/écrire dedans"
                },
                "content" : {
                    "type": "string",
                    "description": "Le contenu à écrire dans le fichier"
                }
            },
            "required": ["path", "content"]
        })

    def handler(self, manager, **kwargs) -> str:
        """ List files """
        path: str = kwargs.get("path")
        content: str = kwargs.get("content")

        manager.stream.debug("\n>>> Call to Write Tool:\n")

        f = open(path, "w+")

        f.write(content)

        res = f.read()

        manager.stream.debug(f"---\n{res}\n---\n")
        return res
