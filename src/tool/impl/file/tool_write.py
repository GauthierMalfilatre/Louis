##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Write tool: create a file, or replace its whole content
##
from tool.tool import Tool
import os
from utils.path import resolve_path, display_path

class WriteTool(Tool):
    def __init__(self):
        super().__init__(
            "write_file",
            "Crée un fichier avec le contenu donné, en créant les dossiers manquants. "
            "Pour modifier une partie d'un fichier existant, utilise plutôt edit_file. "
            "Un fichier existant n'est remplacé que si overwrite vaut true : lis-le "
            "d'abord, car tout son ancien contenu sera perdu.",
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
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Remplacer le fichier s'il existe déjà (défaut : false)"
                    }
                },
                "required": ["path", "content"]
            }
        )

    def handle(self, app, **kwargs) -> str:
        """Create a file, or replace it when overwrite is set."""
        path = kwargs.get("path")
        content = kwargs.get("content")
        # Some models send booleans as strings: bool("false") would be True
        overwrite = str(kwargs.get("overwrite", False)).lower() == "true"

        if not isinstance(path, str) or not path or not isinstance(content, str):
            return "Erreur : 'path' et 'content' sont requis, et doivent être du texte."

        full = resolve_path(app, path)
        if full is None:
            return f"Erreur : '{path}' est en dehors du projet."
        if os.path.isdir(full):
            return f"Erreur : '{path}' est un dossier."
        existed = os.path.exists(full)
        if existed and not overwrite:
            return (f"Erreur : '{path}' existe déjà. Utilise edit_file pour le modifier, "
                    "ou overwrite=true pour remplacer tout son contenu.")

        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8", newline="") as f:
                f.write(content)
        except OSError as e:
            return f"Erreur lors de l'écriture de '{path}' : {e.strerror or e}"

        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        action = "remplacé" if existed else "créé"
        return f"OK : {display_path(full)} {action} ({lines} lignes, {len(content)} caractères)."
