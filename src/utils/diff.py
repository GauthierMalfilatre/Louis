##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Diff utils
##
import difflib

MAX_DIFF_LINES = 60

def diff_preview(before: str, after: str) -> str:
    """ Unified diff of a change, cut after MAX_DIFF_LINES lines """
    lines = list(difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm=""))[2:]
    if not lines:
        return "(aucun changement)"
    if len(lines) > MAX_DIFF_LINES:
        lines = lines[:MAX_DIFF_LINES] + [f"… {len(lines) - MAX_DIFF_LINES} lignes de plus"]
    return "\n".join(lines)
