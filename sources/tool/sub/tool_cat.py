from tool.tools import Tool
import sys
import os

class CatTool(Tool):
    def __init__(self):
        super().__init__("cat_file", "Print a file content", {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Le chemin vers le fichier à afficher"
                }
            },
            "required": ["path"]
        })

    def handler(self, manager, **kwargs) -> str:
        """ List files """
        path: str = kwargs.get("path")
        manager.stream.debug("\n>>> Call to cat Tool:\n")
        f = open(path, "r+")

        res = f.read()

        manager.stream.debug(f"---\n{res}\n---\n")
        return res
