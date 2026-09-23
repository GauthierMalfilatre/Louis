from tool.tools import Tool
import os
from tool.paths import ROOT, get_cwd, resolve_path, display_path


class CDTool(Tool):
    def __init__(self):
        super().__init__(
            "change_directory",
            "Change le dossier courant. Les chemins relatifs des autres tools "
            "(write_file, edit_file, ...) seront résolus depuis ce dossier. "
            "'/' désigne la racine du projet, '..' le dossier parent.",
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Dossier où aller (relatif au dossier courant, ou '/...' depuis la racine du projet)"
                    }
                },
                "required": ["path"]
            }
        )

    def handler(self, manager, **kwargs) -> str:
        """Change the agent's virtual working directory."""
        path = kwargs.get("path")
        if not path:
            return "Erreur : 'path' est requis."

        if path.startswith("/"):
            full = resolve_path(manager, os.path.join(ROOT, path.lstrip("/")))
        else:
            full = resolve_path(manager, path)

        manager.stream.debug(f"\n>>> change_directory: {path}\n")

        if full is None:
            return (f"Erreur : '{path}' est en dehors du projet. "
                    f"Dossier courant inchangé : {display_path(get_cwd(manager))}")
        if not os.path.exists(full):
            return f"Erreur : '{path}' n'existe pas."
        if not os.path.isdir(full):
            return f"Erreur : '{path}' n'est pas un dossier."

        manager.cwd = full
        res = display_path(full)
        manager.stream.debug(f"---\n{res}\n---\n")
        return f"OK : dossier courant = {res}"
