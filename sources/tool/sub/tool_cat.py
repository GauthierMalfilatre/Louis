from tool.tools import Tool
import os
from tool.paths import resolve_path, display_path

MAX_LINES = 400          # lignes max renvoyées par appel
MAX_LINE_LEN = 500       # tronque les lignes très longues (fichiers minifiés, etc.)
MAX_FILE_SIZE = 5_000_000
SHOW_LINE_NUMBERS = True  # mets False si ton modèle recopie les numéros dans old_str


class CatTool(Tool):
    def __init__(self):
        desc = "Affiche le contenu d'un fichier texte. "
        if SHOW_LINE_NUMBERS:
            desc += ("Chaque ligne est préfixée par 'N | ' : ce préfixe ne fait PAS partie "
                    "du fichier, ne le recopie jamais dans edit_file. ")
        desc += (f"Au plus {MAX_LINES} lignes par appel : pour un gros fichier, "
                "utilise start_line et end_line.")
        super().__init__(
            "cat_file",
            desc,
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Chemin du fichier, relatif au dossier courant"
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Première ligne à afficher, à partir de 1 (défaut : 1)"
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Dernière ligne à afficher, incluse (défaut : fin du fichier)"
                    }
                },
                "required": ["path"]
            }
        )

    def handler(self, manager, **kwargs) -> str:
        """Print a file (or a range of lines)."""
        path = kwargs.get("path")
        if not path:
            return "Erreur : 'path' est requis."

        full = resolve_path(manager, path)
        if full is None:
            return f"Erreur : '{path}' est en dehors du projet."
        if not os.path.exists(full):
            return f"Erreur : '{path}' n'existe pas."
        if os.path.isdir(full):
            return f"Erreur : '{path}' est un dossier. Utilise tree pour voir son contenu."
        if os.path.getsize(full) > MAX_FILE_SIZE:
            return f"Erreur : '{path}' est trop gros ({os.path.getsize(full)} octets)."

        manager.stream.debug(f"\n>>> cat_file: {full}\n")

        try:
            with open(full, "r", encoding="utf-8", newline="") as f:
                content = f.read()
        except UnicodeDecodeError:
            return f"Erreur : '{path}' n'est pas un fichier texte UTF-8 (binaire ?)."
        except OSError as e:
            return f"Erreur lors de la lecture de '{path}' : {e.strerror}"

        lines = content.splitlines()
        total = len(lines)
        if total == 0:
            return f"{display_path(full)} (fichier vide)"

        try:
            start = int(kwargs.get("start_line") or 1)
            end = int(kwargs.get("end_line") or total)
        except (TypeError, ValueError):
            return "Erreur : start_line et end_line doivent être des entiers."
        start = max(1, start)
        end = min(total, end)
        if start > total:
            return f"Erreur : start_line={start} mais '{path}' n'a que {total} lignes."
        if start > end:
            return f"Erreur : start_line ({start}) est après end_line ({end})."

        truncated = end - start + 1 > MAX_LINES
        if truncated:
            end = start + MAX_LINES - 1

        width = len(str(end))
        out = []
        for n in range(start, end + 1):
            line = lines[n - 1]
            if len(line) > MAX_LINE_LEN:
                line = line[:MAX_LINE_LEN] + " …[ligne tronquée]"
            out.append(f"{n:>{width}} | {line}" if SHOW_LINE_NUMBERS else line)

        header = f"{display_path(full)} (lignes {start}-{end} sur {total})"
        footer = ""
        if truncated:
            footer = (f"\n… fichier tronqué. Suite avec start_line={end + 1}.")

        res = header + "\n" + "\n".join(out) + footer
        manager.stream.debug(f"---\n{res}\n---\n")
        return res