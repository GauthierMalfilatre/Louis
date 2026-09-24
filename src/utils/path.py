##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Path utils
##
import os

ROOT = os.path.realpath(os.getcwd())

def get_cwd(manager) -> str:
    if not hasattr(manager, "cwd"):
        manager.cwd = ROOT
    return manager.cwd

def resolve_path(manager, path: str) -> str | None:
    if os.path.isabs(path):
        full = os.path.realpath(path)
        # "/src/main.py" is how display_path shows a file: from the project root, not the disk's
        if os.path.commonpath([full, ROOT]) != ROOT:
            full = os.path.realpath(os.path.join(ROOT, path.lstrip("/")))
    else:
        full = os.path.realpath(os.path.join(get_cwd(manager), path))
    if os.path.commonpath([full, ROOT]) != ROOT:
        return None
    return full

def display_path(full: str) -> str:
    rel = os.path.relpath(full, ROOT)
    return "/" if rel == "." else "/" + rel.replace(os.sep, "/")
