from tool.tools import Tool
import sys
import os

class LSTool(Tool):
    def __init__(self):
        super().__init__("list_directory", "Liste les fichiers et les dossiers du dossier courant", {
            "type": "object",
            "properties": {},
            "required": []
        })

    def handler(self, manager, **kwargs) -> str:
        """ List files """
        manager.stream.debug("\n>>> Call to ls Tool:\n")
        res = str(os.listdir())
        manager.stream.debug(f"---\n{res}\n---\n")
        return res
