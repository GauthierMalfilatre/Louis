##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Risk of a tool call: what it changes, whether it can be undone, and how
##
from dataclasses import dataclass
import os
import subprocess
import utils.path

# From the least to the most: a call that changes nothing, one that can be undone, one that can not
SAFE        : str = "safe"
REVERSIBLE  : str = "reversible"
IRREVERSIBLE: str = "irreversible"
LEVELS: tuple[str, ...] = (SAFE, REVERSIBLE, IRREVERSIBLE)

@dataclass(frozen=True)
class Risk:
    """
        What a tool call would do, judged before it runs: its level, what follows from it, and how to undo it. The
        texts are shown to the user. An irreversible call has no undo: what can be done after it (closing a pull
        request) leaves its trace, it is told in its consequence
    """
    level      : str = SAFE
    consequence: str = ""
    undo       : str = ""

    def at_least(self, level: str) -> bool:
        """ Whether the call is as risky as level, or more """
        return LEVELS.index(self.level) >= LEVELS.index(level)

NONE: Risk = Risk()

def file_state(full: str) -> str:
    """
        What git keeps of a file of the project: "clean" (committed as it is now), "modified" (changed since its last
        commit), "untracked" (git has no copy of it, an ignored file too), or "none" outside a git repository
    """
    root: str = utils.path.ROOT
    def git(*args: str) -> subprocess.CompletedProcess | None:
        try:
            return subprocess.run(["git", *args], cwd=root, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  timeout=10, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        except (OSError, subprocess.TimeoutExpired):
            return None
    path: str = os.path.relpath(full, root)
    inside = git("rev-parse", "--is-inside-work-tree")
    if inside is None or inside.returncode != 0:
        return "none"
    tracked = git("ls-files", "--error-unmatch", "--", path)
    if tracked is None or tracked.returncode != 0:
        return "untracked"
    changed = git("status", "--porcelain", "--", path)
    return "clean" if changed is not None and not changed.stdout.strip() else "modified"

def change_risk(full: str) -> Risk:
    """
        A file of the project its content is changed in: reversible while git has it as it is now, irreversible
        when what it holds now is nowhere else (never committed, or changed since)
    """
    shown: str = utils.path.display_path(full)
    match file_state(full):
        case "clean":
            return Risk(REVERSIBLE, f"{shown} sera modifié", f"git restore {os.path.relpath(full, utils.path.ROOT)}")
        case "modified":
            return Risk(IRREVERSIBLE, f"{shown} sera modifié, et ses changements non commités perdus : git ne les a pas")
        case _:
            return Risk(IRREVERSIBLE, f"{shown} sera modifié, et son contenu actuel perdu : git n'en a aucune copie")
