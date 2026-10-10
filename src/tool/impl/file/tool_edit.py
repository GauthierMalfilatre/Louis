from tool.tool import Tool
from tool.risk import Risk, NONE, change_risk
import ast
import difflib
import os
import re
import warnings
from utils.path import resolve_path, display_path
from utils.diff import diff_preview
from tool.impl.file.tool_write import fix_newlines, NEWLINES_NOTE

CONTEXT_LINES = 3

# What to do instead of an edit that changes nothing: small models send one when they do not know yet what to change
NO_CHANGE = ("Si tu sais quoi changer, mets dans new_str le code corrigé. Sinon, n'appelle pas edit_file : cherche la "
             "cause avec search ou cat_file, ou explique à l'utilisateur ce que tu as trouvé.")
CLOSEST_MAX_LINES = 15      # An old_str longer than this is the whole file, or nearly: no passage to show
CLOSEST_MIN_RATIO = 0.5     # Below, the passage found is not close enough to help
CLOSEST_FILE_LINES = 2000   # Bigger files are not searched for it

# The line numbers cat_file puts before each line ("  3 | "): small models copy them into old_str
LINE_NUMBER = re.compile(r"^\s*\d+ \|(?: |$)")

def line_of(text: str, index: int) -> int:
    """1-based line number of a character index."""
    return text.count("\n", 0, index) + 1

def without_line_numbers(text: str) -> str:
    """ The text without the line numbers of cat_file, if every one of its lines has one """
    lines = text.split("\n")
    written = [line for line in lines if line]
    if not written or not all(LINE_NUMBER.match(line) for line in written):
        return text
    return "\n".join(LINE_NUMBER.sub("", line) for line in lines)

def unescaped(text: str) -> str:
    """
        The text a model escaped once too many ("\\n" written for a newline): with no real newline in it, its
        \\n, \\t and \\" become what they stand for. A text with real newlines meant its escapes, it is kept
    """
    if "\n" in text:
        return text
    return text.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')

def closest(text: str, needle: str) -> tuple[int, list[str]] | None:
    """
        The lines of text most like needle, with one more line before and after to show how the file is
        cut, and the number of the first one: None if none is close
    """
    lines = text.splitlines()
    size = max(1, len(needle.splitlines()))
    if not lines or len(lines) > CLOSEST_FILE_LINES:
        return None
    best, where = 0.0, 0
    for start in range(max(1, len(lines) - size + 1)):
        ratio = difflib.SequenceMatcher(None, "\n".join(lines[start:start + size]), needle, autojunk=False).ratio()
        if ratio > best:
            best, where = ratio, start
    if best < CLOSEST_MIN_RATIO:
        return None
    first, last = max(0, where - 1), min(len(lines), where + size + 1)
    return first + 1, lines[first:last]

def broken_syntax(path: str, before: str, after: str) -> str | None:
    """
        Why a Python file valid before an edit would not be after it ("ligne 18 : unterminated string literal"). None
        if it still is, if it was not already (the edit may be fixing it), or if it is not Python
    """
    if not path.endswith(".py"):
        return None
    # The warnings of the code parsed (an invalid escape...) are none of Louis's business
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            ast.parse(before)
        except (SyntaxError, ValueError):
            return None
        try:
            ast.parse(after)
        except SyntaxError as e:
            lines: list[str] = after.splitlines()
            code: str = lines[e.lineno - 1].strip()[:120] if e.lineno and e.lineno <= len(lines) else ""
            return f"ligne {e.lineno} : {e.msg}" + (f", dans « {code} »" if code else "")
        except ValueError as e:
            return str(e)
    return None

def indentation(line: str) -> str:
    """ The spaces and tabs a line starts with """
    return line[:len(line) - len(line.lstrip())]

def reindented(text: str, old_str: str, new_str: str) -> tuple[str, str] | None:
    """
        old_str as the file has it and new_str shifted as much, when old_str is in the file only with every line
        shifted by the same indentation: small models lose count of the spaces of nested code. None if it is not,
        or is at several places
    """
    old_lines: list[str] = old_str.split("\n")
    tail: bool = len(old_lines) > 1 and old_lines[-1] == ""
    if tail:
        old_lines.pop()
    written: list[int] = [n for n, line in enumerate(old_lines) if line.strip()]
    if not written:
        return None
    lines: list[str] = text.split("\n")
    found: list[tuple[int, str, str]] = []
    for start in range(len(lines) - len(old_lines) + 1):
        window: list[str] = lines[start:start + len(old_lines)]
        # The shift, from the first written line: indentation the file adds to old_str, or cuts from it
        have, want = indentation(window[written[0]]), indentation(old_lines[written[0]])
        if have.endswith(want):
            add, cut = have[:len(have) - len(want)], ""
        elif want.endswith(have):
            add, cut = "", want[:len(want) - len(have)]
        else:
            continue
        # The same indentation: the exact search already failed, it is another text
        if not add and not cut:
            continue
        if all(got.strip() == "" if not line.strip() else
               line.startswith(cut) and got.rstrip() == add + line[len(cut):].rstrip()
               for line, got in zip(old_lines, window)):
            found.append((start, add, cut))
    if len(found) != 1:
        return None

    start, add, cut = found[0]
    def shifted(line: str) -> str:
        if not line.strip():
            return line
        return add + (line[len(cut):] if line.startswith(cut) else line.lstrip())
    passage: str = "\n".join(lines[start:start + len(old_lines)]) + ("\n" if tail else "")
    return passage, "\n".join(shifted(line) for line in new_str.split("\n"))

def not_found(path: str, text: str, old_str: str) -> str:
    """ Why old_str is not in the file, with the passage the model surely meant, to copy it exactly """
    message = f"Erreur : 'old_str' introuvable dans '{path}'."
    # Searched as the model meant it: its lines, not its line numbers or its escapes
    old_str = unescaped(without_line_numbers(old_str))
    if len(old_str.splitlines()) > CLOSEST_MAX_LINES:
        return (f"{message} Ne recopie pas tout le fichier : mets dans old_str seulement les quelques lignes "
                "à changer, un appel par endroit. Pour réécrire tout le fichier, utilise write_file avec overwrite=true.")
    found = closest(text, old_str)
    if found is None:
        return f"{message} Relis le fichier avec cat_file, puis copie le texte exact, sans les numéros « N | »."
    first, lines = found
    passage = "\n".join(f"{first + n:>4} | {line}" for n, line in enumerate(lines))
    return (f"{message} Le passage le plus proche (lignes {first}-{first + len(lines) - 1}) est :\n{passage}\n"
            "Recopie-le exactement dans old_str (espaces et retours à la ligne compris), sans les numéros « N | ».")

class EditTool(Tool):
    def __init__(self):
        super().__init__(
            "edit_file",
            "Modifie une partie d'un fichier existant : old_str, un passage exact du fichier, est remplacé "
            "par new_str. Mets dans old_str seulement les lignes à changer (plus une ou deux autour si elles "
            "ne sont pas uniques), jamais tout le fichier : pour tout réécrire, utilise write_file avec "
            "overwrite=true. Pour changer plusieurs endroits, fais un appel par endroit. Pour AJOUTER du "
            "texte sans rien supprimer, mets dans old_str une ligne existante, et dans new_str cette même "
            "ligne suivie du texte ajouté. old_str doit "
            "correspondre EXACTEMENT au fichier (espaces, indentation et retours à la ligne compris), sans "
            "les numéros « N | » de cat_file, et être unique sauf si replace_all vaut true. "
            "Lis le fichier avant de l'éditer. new_str est le code APRÈS ta modification : il doit être différent "
            "d'old_str. Si tu ne sais pas encore quoi changer, n'appelle pas edit_file : cherche la cause avec "
            "search ou cat_file, ou explique à l'utilisateur ce que tu as trouvé.",
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Chemin du fichier, relatif au dossier courant"
                    },
                    "old_str": {
                        "type": "string",
                        "description": "Les quelques lignes exactes à remplacer, pas tout le fichier"
                    },
                    "new_str": {
                        "type": "string",
                        "description": "Le code après ta modification, différent d'old_str (vide pour supprimer "
                                       "old_str)"
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "Remplacer toutes les occurrences (défaut : false)"
                    }
                },
                "required": ["path", "old_str", "new_str"]
            }
        )

    def risk(self, manager, **kwargs) -> Risk:
        """ The file changed: reversible while git has it as it is now """
        path = kwargs.get("path")
        full = resolve_path(manager, path) if isinstance(path, str) and path else None
        return change_risk(full) if full is not None and os.path.isfile(full) else NONE

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

        full = resolve_path(manager, path)
        if full is None:
            return f"Erreur : '{path}' est en dehors du projet."
        if os.path.isdir(full):
            return f"Erreur : '{path}' est un dossier."

        try:
            with open(full, "r", encoding="utf-8", newline="") as f:
                text = f.read()
        except FileNotFoundError:
            return f"Erreur : '{path}' n'existe pas. Utilise write_file pour le créer."
        except (OSError, UnicodeDecodeError) as e:
            return f"Erreur lors de la lecture de '{path}' : {e}"

        # old_str must be copied from the file as it is: not remembered, guessed, or pieced from search results
        seen = getattr(manager, "seen_files", None)
        state = seen.state(full) if seen is not None else "seen"
        if state == "unseen":
            return (f"Erreur : lis d'abord '{path}' avec cat_file. old_str doit être copié de son contenu exact, "
                    "pas écrit de mémoire ni recollé depuis des résultats de search.")
        if state == "changed":
            return (f"Erreur : '{path}' a changé depuis ta dernière lecture. "
                    "Relis-le avec cat_file avant de le modifier.")

        if "\r\n" in text and "\r\n" not in old_str:
            old_str = old_str.replace("\n", "\r\n")
            new_str = new_str.replace("\n", "\r\n")

        # Checked once the file is read: a call that changes nothing must never pass for a sign the code is right
        if old_str == new_str:
            if old_str in text:
                return ("Erreur : old_str et new_str sont identiques : cet appel ne change rien, le fichier n'a PAS "
                        f"été modifié. Ce n'est pas la preuve que le code est juste. {NO_CHANGE}")
            return ("Erreur : old_str et new_str sont identiques, et ce passage n'est même pas dans le fichier : tu "
                    f"l'as écrit de mémoire. Rien n'a été modifié. {NO_CHANGE}")

        count = text.count(old_str)
        # Copied from cat_file with its line numbers, or escaped once too many: repaired the same way in
        # both texts, as long as the repaired old_str is really in the file
        for repair in (without_line_numbers, unescaped):
            if count == 0 and (repaired := repair(old_str)) != old_str and repaired in text:
                old_str, new_str = repaired, repair(new_str)
                count = text.count(old_str)
        # Indented a few spaces off: found with the indentation of the file, new_str shifted as much
        reindent_note = ""
        if count == 0 and (shifted := reindented(text, old_str, new_str)) is not None:
            old_str, new_str = shifted
            count = text.count(old_str)
            reindent_note = ("\nNote : ton old_str n'avait pas l'indentation du fichier. Il a été retrouvé, et new_str "
                             "décalé d'autant. Copie l'indentation exacte la prochaine fois.")
        if count == 0:
            return not_found(path, text, old_str)
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
        fixed = fix_newlines(full, new_text)
        # Checked before asking the user: a broken edit is never shown to them
        if broken := broken_syntax(full, text, fixed):
            return (f"Erreur : cette modification casserait la syntaxe de '{path}' ({broken}). Rien n'a été "
                    "modifié : corrige new_str (guillemets, parenthèses, indentation), puis rappelle edit_file.")

        if not manager.permissions.request(self.name, f"Modification de {display_path(full)}", diff_preview(text, fixed)):
            return (f"Refusé : l'utilisateur n'a pas autorisé la modification de '{path}'. "
                    "Ne la retente pas : demande-lui ce qu'il veut à la place.")

        try:
            with open(full, "w", encoding="utf-8", newline="") as f:
                f.write(fixed)
        except OSError as e:
            return f"Erreur lors de l'écriture de '{path}' : {e}"
        # The model knows the file as it wrote it: it can edit it again without reading it
        if seen is not None:
            seen.mark(full)

        all_lines = fixed.splitlines()
        start_line = line_of(fixed, first)
        end_line = start_line + new_str.count("\n")
        lo = max(1, start_line - CONTEXT_LINES)
        hi = min(len(all_lines), end_line + CONTEXT_LINES)
        snippet = "\n".join(f"{n:>5} | {all_lines[n - 1]}" for n in range(lo, hi + 1))

        what = f"{count} occurrences remplacées" if replace_all else "1 occurrence remplacée"
        return (f"OK : {what} dans {display_path(full)}.\n{snippet}{NEWLINES_NOTE if fixed != new_text else ''}"
                f"{reindent_note}")
