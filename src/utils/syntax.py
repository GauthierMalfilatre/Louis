##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Syntax utils: check the Python code the model is about to write
##
import ast

MAX_REPAIRS = 100

def python_error(code: str) -> SyntaxError | None:
    """ The syntax error of some Python code, None when it is valid """
    try:
        ast.parse(code)
    except SyntaxError as e:
        return e
    return None

def repair_newlines(code: str) -> tuple[str, int]:
    """
        Small models often write the newline escape of a Python string as a real newline in the
        JSON of a tool call: it cuts the string in two, which is never valid. Put the escape back
        where a string is cut, and give the count of repairs. The code comes back untouched,
        with 0 repairs, unless the repaired code is valid.
    """
    lines: list[str] = code.split("\n")
    for repairs in range(MAX_REPAIRS):
        error: SyntaxError | None = python_error("\n".join(lines))
        if error is None:
            return "\n".join(lines), repairs
        # Only a string cut by a newline: a triple-quoted one may hold newlines, it is missing its end
        cut: bool = error.msg.startswith("unterminated") and "triple-quoted" not in error.msg
        if not cut or not error.lineno or error.lineno >= len(lines):
            break
        index: int = error.lineno - 1
        lines[index:index + 2] = [lines[index] + "\\n" + lines[index + 1]]
    return code, 0

def check_python(path: str, content: str) -> tuple[str, int, SyntaxError | None]:
    """
        Check the new content of a file: the code to write, the count of repaired newlines, and the
        syntax error left, even one that was already there. Only Python files are checked.
    """
    if not path.endswith(".py"):
        return content, 0, None
    code, repairs = repair_newlines(content)
    return code, repairs, python_error(code)

def syntax_warning(error: SyntaxError | None) -> str:
    """ Tell the user, in the permission request, that the code is invalid """
    return f" (attention : erreur de syntaxe ligne {error.lineno})" if error else ""

def syntax_note(repairs: int, error: SyntaxError | None) -> str:
    """ Tell the model what was repaired, and what it must fix """
    note: str = ""
    if repairs:
        note += (f"\nNote : {repairs} retour(s) à la ligne au milieu d'une chaîne remplacé(s) par \\n. "
                 "Relis le fichier avant de le modifier à nouveau.")
    if error:
        note += (f"\nAttention : erreur de syntaxe ligne {error.lineno} : {error.msg}. "
                 "Relis cette ligne et corrige-la avec edit_file.")
    return note
