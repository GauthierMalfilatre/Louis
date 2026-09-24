##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Mkdir tool: create a folder, with its missing parents
##
from tool.tool import Tool
import os
from utils.path import resolve_path, display_path

class MkdirTool(Tool):
    def __init__(self):
        super().__init__(
            "mkdir",
            "Crée un dossier, avec ses dossiers parents manquants. write_file crée déjà les "
            "dossiers dont un fichier a besoin : n'utilise mkdir que pour un dossier vide.",
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Chemin du dossier, relatif au dossier courant"
                    }
                },
                "required": ["path"]
            }
        )

    def handle(self, app, **kwargs) -> str:
        """Create a folder and its missing parents."""
        path = kwargs.get("path")
        if not isinstance(path, str) or not path:
            return "Erreur : 'path' est requis, et doit être du texte."

        full = resolve_path(app, path)
        if full is None:
            return f"Erreur : '{path}' est en dehors du projet."
        if os.path.isdir(full):
            return f"OK : {display_path(full)} existe déjà."
        if os.path.exists(full):
            return f"Erreur : '{path}' existe déjà, et c'est un fichier."

        if not app.permissions.request(self.name, f"Création du dossier {display_path(full)}"):
            return (f"Refusé : l'utilisateur n'a pas autorisé la création de '{path}'. "
                    "Ne la retente pas : demande-lui ce qu'il veut à la place.")

        try:
            os.makedirs(full, exist_ok=True)
        except OSError as e:
            return f"Erreur lors de la création de '{path}' : {e.strerror or e}"
        return f"OK : dossier {display_path(full)} créé."
