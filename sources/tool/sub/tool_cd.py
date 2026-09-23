from tool.tools import Tool
import sys
import os

class CDTool(Tool):
    def __init__(self):
        super().__init__("change_directory", "Change le dossier courant", {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Le chemin vers le dossier où aller"
                }
            },
            "required": ["path"]
        })

    def handler(self, manager, **kwargs) -> str:
        """ List files """
        path: str = kwargs.get("path")
        manager.stream.debug("\n>>> Call to cd Tool:\n")
        str(os.chdir(path))
        res = os.curdir
        manager.stream.debug(f"---\n{res}\n---\n")
        return res
