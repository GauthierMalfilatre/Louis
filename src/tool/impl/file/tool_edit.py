from tool.tool import Tool
import os
from utils.path import resolve_path, display_path
from utils.diff import diff_preview

CONTEXT_LINES = 3

def line_of(text: str, index: int) -> int:
    """1-based line number of a character index."""
    return text.count("\n", 0, index) + 1

class EditTool(Tool):
    def __init__(self):
        super().__init__(
            "edit_file",
            "Modifie un fichier existant en remplaçant un texte exact par un autre. "
            "old_str doit correspondre EXACTEMENT au contenu du fichier (espaces, "
            "indentation et retours à la ligne compris) et être unique dans le fichier, "
            "sauf si replace_all vaut true. Inclus quelques lignes autour du passage "
            "à modifier pour le rendre unique. Lis le fichier avant de l'éditer.",
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Chemin du fichier, relatif au dossier courant"
                    },
                    "old_str": {
                        "type": "string",
                        "description": "Texte exact à remplacer"
                    },
                    "new_str": {
                        "type": "string",
                        "description": "Texte de remplacement (vide pour supprimer old_str)"
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "Remplacer toutes les occurrences (défaut : false)"
                    }
                },
                "required": ["path", "old_str", "new_str"]
            }
        )

    def handle(self, manager, **kwargs) -> str:
        """Replace an exact string in a file."""
        path = kwargs.get("path")
        old_str = kwargs.get("old_str")
        new_str = kwargs.get("new_str")
        replace_all = bool(kwargs.get("replace_all", False))

        if not path or old_str is None or new_str is None:
            return "Erreur : 'path', 'old_str' et 'new_str' sont requis."
        if old_str == "":
            return "Erreur : 'old_str' ne peut pas être vide. Pour créer un fichier, utilise write_file."
        if old_str == new_str:
            return "Erreur : 'old_str' et 'new_str' sont identiques, rien à modifier."

        full = resolve_path(manager, path)
        if full is None:
            return f"Erreur : '{path}' est en dehors du projet."
        if os.path.isdir(full):
            return f"Erreur : '{path}' est un dossier."

        manager.stream.debug(f"\n>>> edit_file: {full}\n")

        try:
            with open(full, "r", encoding="utf-8", newline="") as f:
                text = f.read()
        except FileNotFoundError:
            return f"Erreur : '{path}' n'existe pas. Utilise write_file pour le créer."
        except (OSError, UnicodeDecodeError) as e:
            return f"Erreur lors de la lecture de '{path}' : {e}"

        if "\r\n" in text and "\r\n" not in old_str:
            old_str = old_str.replace("\n", "\r\n")
            new_str = new_str.replace("\n", "\r\n")

        count = text.count(old_str)
        if count == 0:
            return (f"Erreur : 'old_str' introuvable dans '{path}'. Vérifie l'indentation "
                    "et les espaces, puis relis le fichier pour copier le texte exact.")
        if count > 1 and not replace_all:
            lines, start = [], 0
            while (idx := text.find(old_str, start)) != -1:
                lines.append(str(line_of(text, idx)))
                start = idx + 1
            return (f"Erreur : 'old_str' apparaît {count} fois dans '{path}' "
                    f"(lignes {', '.join(lines)}). Ajoute du contexte pour le rendre "
                    "unique, ou mets replace_all à true.")

        first = text.find(old_str)
        new_text = text.replace(old_str, new_str) if replace_all else text.replace(old_str, new_str, 1)

        if not manager.permissions.request(self.name, f"Modification de {display_path(full)} :", diff_preview(text, new_text)):
            return (f"Refusé : l'utilisateur n'a pas autorisé la modification de '{path}'. "
                    "Ne la retente pas : demande-lui ce qu'il veut à la place.")

        try:
            with open(full, "w", encoding="utf-8", newline="") as f:
                f.write(new_text)
        except OSError as e:
            return f"Erreur lors de l'écriture de '{path}' : {e}"

        all_lines = new_text.splitlines()
        start_line = line_of(new_text, first)
        end_line = start_line + new_str.count("\n")
        lo = max(1, start_line - CONTEXT_LINES)
        hi = min(len(all_lines), end_line + CONTEXT_LINES)
        snippet = "\n".join(f"{n:>5} | {all_lines[n - 1]}" for n in range(lo, hi + 1))

        what = f"{count} occurrences remplacées" if replace_all else "1 occurrence remplacée"
        res = f"OK : {what} dans {display_path(full)}.\n{snippet}"
        manager.stream.debug(f"---\n{res}\n---\n")
        return res
