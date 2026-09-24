from bootstrap.sources.tool.tools import Tool
import os
from bootstrap.sources.tool.paths import resolve_path, display_path

class WriteTool(Tool):
    def __init__(self):
        super().__init__(
            "write_file",
            "Crée un fichier ou ÉCRASE entièrement son contenu. "
            "Pour modifier une partie d'un fichier existant, utilise plutôt edit_file.",
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Chemin du fichier, relatif au dossier courant"
                    },
                    "content": {
                        "type": "string",
                        "description": "Contenu complet du fichier"
                    }
                },
                "required": ["path", "content"]
            }
        )

    def handler(self, manager, **kwargs) -> str:
        """Write content to a file (overwrite)."""
        path = kwargs.get("path")
        content = kwargs.get("content")
        if not path or content is None:
            return "Erreur : 'path' et 'content' sont requis."

        full = resolve_path(manager, path)
        if full is None:
            return f"Erreur : '{path}' est en dehors du projet."
        if os.path.isdir(full):
            return f"Erreur : '{path}' est un dossier."

        manager.stream.debug(f"\n>>> write_file: {full}\n")

        existed = os.path.exists(full)
        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            return f"Erreur lors de l'écriture de '{path}' : {e}"

        n_lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        action = "écrasé" if existed else "créé"
        res = f"OK : {display_path(full)} {action} ({n_lines} lignes, {len(content)} caractères)."
        manager.stream.debug(f"---\n{res}\n---\n")
        return res
