##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## The project Louis runs in, as a few hints: its name, and the files the user is working on
##
import os
import re
import subprocess

# The files the user works on: those changed in git, or else the ones touched last, never those of Louis itself nor of
# the tools of the project (what the web page suggests, what the scribe welcomes with). At most FILES_LOOKED files are
# looked at, for a big folder
SKIPPED_DIRS : frozenset[str] = frozenset({"node_modules", "__pycache__", "venv", "dist", "build", "target", "exports"})
SKIPPED_FILES: re.Pattern = re.compile(r"^louis\.|\.(db|db-journal|log|jsonl|pyc|lock)$")
FILES_LOOKED : int = 2000
HINTS        : int = 3

def kept(path: str) -> bool:
    """ A file worth suggesting: not Louis's own (its database, its log...), nor hidden """
    name: str = os.path.basename(path)
    return not name.startswith(".") and not SKIPPED_FILES.search(name)

def changed_files(cwd: str) -> list[str] | None:
    """ The files changed or added in git, relative to cwd as git status gives them: None out of a repository """
    try:
        status = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=cwd, capture_output=True, text=True,
                                timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None
    if status.returncode != 0:
        return None
    files: list[str] = []
    for line in status.stdout.splitlines():
        path: str = line[3:].split(" -> ")[-1].strip('"')
        # A deleted file is nothing to work on, an untracked folder is not a file
        if "D" not in line[:2] and kept(path) and os.path.isfile(os.path.join(cwd, path)):
            files.append(path)
    return files

def recent_files(cwd: str) -> list[str]:
    """ The files touched last in cwd, out of hidden folders and those of the tools (venv, node_modules...) """
    found: list[tuple[float, str]] = []
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [folder for folder in dirs if not folder.startswith(".") and folder not in SKIPPED_DIRS]
        for name in files:
            path: str = os.path.join(root, name)
            if kept(path):
                try:
                    found.append((os.path.getmtime(path), os.path.relpath(path, cwd)))
                except OSError:
                    continue
            if len(found) >= FILES_LOOKED:
                break
        if len(found) >= FILES_LOOKED:
            break
    return [path for _, path in sorted(found, reverse=True)[:HINTS]]

def project(cwd: str) -> dict:
    """ What the empty page suggests from: the name of the folder, and the files changed in git, or touched last """
    changed: list[str] | None = changed_files(cwd)
    return {"name": os.path.basename(os.path.abspath(cwd)), "changed": (changed or [])[:HINTS],
            "recent": [] if changed else recent_files(cwd)}
