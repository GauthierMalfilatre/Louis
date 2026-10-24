##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Write tool: create a file, or replace its whole content
##
from tool.tool import Tool
from tool.risk import Risk, NONE, REVERSIBLE, change_risk
import ast
import os
from utils.path import resolve_path, display_path
from utils.diff import diff_preview

NEWLINES_NOTE = ("\nNote : des retours à la ligne qui coupaient une chaîne ont été reformatés en \\n. "
                 "Relis le fichier avant de le modifier à nouveau.")

def fix_newlines(path: str, code: str) -> str:
    """
        Small models often write the newline escape of a Python string as a real newline in the JSON
        of a tool call, which cuts the string in two. Reformat these newlines as \\n, line after line.
        The code comes back untouched unless it becomes valid, and so do valid code and other files.
    """
    if not path.endswith(".py"):
        return code
    lines = code.split("\n")
    for _ in range(100):
        try:
            ast.parse("\n".join(lines))
            return "\n".join(lines)
        except SyntaxError as e:
            # Only a string cut at the end of a line: a triple-quoted string may hold newlines
            if not e.msg.startswith("unterminated") or "triple-quoted" in e.msg \
                    or not e.lineno or e.lineno >= len(lines):
                return code
            lines[e.lineno - 1:e.lineno + 1] = [lines[e.lineno - 1] + "\\n" + lines[e.lineno]]
    return code

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

    def risk(self, app, **kwargs) -> Risk:
        """ A new file can be removed again; a file replaced loses its content, unless git has it as it is now """
        path = kwargs.get("path")
        full = resolve_path(app, path) if isinstance(path, str) and path else None
        if full is None or os.path.isdir(full):
            return NONE
        content = kwargs.get("content")
        content = fix_newlines(full, content) if isinstance(content, str) else ""
        if not os.path.exists(full):
            shown: str = display_path(full)
            return Risk(REVERSIBLE, f"{shown} sera créé", f"supprimer {shown}", diff_preview("", content))
        # Without overwrite, the tool refuses: nothing is written
        if str(kwargs.get("overwrite", False)).lower() != "true":
            return NONE
        try:
            with open(full, "r", encoding="utf-8", newline="") as f:
                before = f.read()
        except (OSError, UnicodeDecodeError):
            before = ""
        return change_risk(full, diff_preview(before, content))

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

        before = ""
        if existed:
            try:
                with open(full, "r", encoding="utf-8", newline="") as f:
                    before = f.read()
            except (OSError, UnicodeDecodeError):
                pass
        fixed = fix_newlines(full, content)
        summary = f"{'Remplacement' if existed else 'Création'} de {display_path(full)}"
        if not app.permissions.request(self.name, summary, diff_preview(before, fixed)):
            return (f"Refusé : l'utilisateur n'a pas autorisé l'écriture de '{path}'. "
                    "Ne la retente pas : demande-lui ce qu'il veut à la place.")

        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8", newline="") as f:
                f.write(fixed)
        except OSError as e:
            return f"Erreur lors de l'écriture de '{path}' : {e.strerror or e}"
        # The model knows the file as it wrote it: edit_file may change it without reading it first
        seen = getattr(app, "seen_files", None)
        if seen is not None:
            seen.mark(full)

        lines = fixed.count("\n") + (1 if fixed and not fixed.endswith("\n") else 0)
        action = "remplacé" if existed else "créé"
        return (f"OK : {display_path(full)} {action} ({lines} lignes, {len(fixed)} caractères)."
                f"{NEWLINES_NOTE if fixed != content else ''}")
