##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Artifacts: the files the model wrote in a session, rebuilt from its tool calls or read on the disk
##
from tool.tool import failed
from tool.impl.file.tool_write import fix_newlines
from tool.impl.file.tool_edit import without_line_numbers, unescaped
import os

# The tools that write a file, and the arguments they take
WRITERS: frozenset[str] = frozenset({"write_file", "edit_file"})

# Characters of a file read on the disk, at most: past them, its content is left out
MAX_CHARS: int = 200_000

# The language of a code block, by the extension of the file
LANGUAGES: dict[str, str] = {
    "py": "python", "js": "javascript", "ts": "typescript", "jsx": "jsx", "tsx": "tsx", "json": "json",
    "md": "markdown", "html": "html", "css": "css", "sh": "bash", "bash": "bash", "c": "c", "h": "c",
    "cpp": "cpp", "hpp": "cpp", "java": "java", "go": "go", "rs": "rust", "rb": "ruby", "php": "php",
    "yml": "yaml", "yaml": "yaml", "toml": "toml", "sql": "sql", "xml": "xml", "co": "colang",
}

def located(cwd: str, path: str) -> str | None:
    """
        Where a path given to a tool is, as resolve_path finds it in the folder of the session: "/src/main.py" is
        from the root of the project, not of the disk. None out of the project, as the tool refused it
    """
    root: str = os.path.abspath(cwd)
    full: str = os.path.normpath(path if os.path.isabs(path) else os.path.join(root, path))
    if os.path.isabs(path) and os.path.commonpath([full, root]) != root:
        full = os.path.normpath(os.path.join(root, path.lstrip("/")))
    return full if os.path.commonpath([full, root]) == root else None

def shown(full: str, cwd: str) -> str:
    """ A file as the tools show it: from the root of the project, /src/main.py """
    return "/" + os.path.relpath(full, os.path.abspath(cwd)).replace(os.sep, "/")

def language(path: str) -> str:
    """ The language of a file, for its code block: "" if it is not known """
    return LANGUAGES.get(os.path.splitext(path)[1].lstrip(".").lower(), "")

def edited(full: str, text: str, arguments: dict) -> str | None:
    """
        The text after an edit_file call, made the way the tool made it: its line endings, its repairs of old_str,
        its newlines. None if old_str is not in the text: it was not the file the tool edited
    """
    old, new = arguments.get("old_str"), arguments.get("new_str")
    if not isinstance(old, str) or not isinstance(new, str) or not old:
        return None
    if "\r\n" in text and "\r\n" not in old:
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    count: int = text.count(old)
    for repair in (without_line_numbers, unescaped):
        if count == 0 and (repaired := repair(old)) != old and repaired in text:
            old, new = repaired, repair(new)
            count = text.count(old)
    if count == 0:
        return None
    # As the tool reads it: bool("false") is True there too
    every: bool = bool(arguments.get("replace_all", False))
    return fix_newlines(full, text.replace(old, new) if every else text.replace(old, new, 1))

def on_disk(full: str) -> str | None:
    """ The content of a file now, None if it is not there, not text, or too big """
    try:
        if os.path.getsize(full) > MAX_CHARS * 4:
            return None
        with open(full, "r", encoding="utf-8", newline="") as file:
            content: str = file.read()
    except (OSError, UnicodeDecodeError):
        return None
    return content if len(content) <= MAX_CHARS else None

def collect(messages: list[dict], cwd: str) -> list[dict]:
    """
        The files written in the messages of a document (their tool calls with their results), in the order they
        were first written: {"path", "language", "action" ("created" or "modified"), "writes" (successful calls),
        "source", "content" (None when missing)}. The database keeps the calls, not the files: write_file gives the
        whole content, each edit_file is played again on it as the tool did. source tells where the content is from:
        "session" (rebuilt from the calls), "disk" (only edited, so there before the session, or its edits no longer
        apply: read now, it may have changed since) or "missing" (neither)
    """
    files: dict[str, dict] = {}
    for message in messages:
        for call in message.get("tools", []):
            arguments: dict = call.get("arguments") or {}
            path = arguments.get("path")
            # Only what was done: a refused, failed or cancelled call changed nothing
            if call["name"] not in WRITERS or not isinstance(path, str) or not path \
                    or call.get("result") is None or failed(call["result"]) or not call["result"].startswith("OK"):
                continue
            full: str | None = located(cwd, path)
            if full is None:
                continue
            file: dict = files.setdefault(full, {"text": None, "broken": False, "writes": 0, "created": None})
            file["writes"] += 1
            if call["name"] == "write_file":
                content = arguments.get("content")
                file["text"] = fix_newlines(full, content) if isinstance(content, str) else None
                file["broken"] = file["text"] is None
                if file["created"] is None:
                    file["created"] = " créé " in call["result"].split("\n", 1)[0]
            else:
                file["created"] = bool(file["created"])
                if file["text"] is not None and not file["broken"]:
                    file["text"] = edited(full, file["text"], arguments)
                    file["broken"] = file["text"] is None

    artifacts: list[dict] = []
    for full, file in files.items():
        content: str | None = file["text"] if not file["broken"] else None
        source: str = "session"
        if content is None:
            content = on_disk(full)
            source = "disk" if content is not None else "missing"
        artifacts.append({
            "path"    : shown(full, cwd),
            "language": language(full),
            "action"  : "created" if file["created"] else "modified",
            "writes"  : file["writes"],
            "source"  : source,
            "content" : content,
        })
    return artifacts

def find(artifacts: list[dict], cwd: str, path: str) -> dict | None:
    """ The artifact of a path typed by the user (pendu.py, /src/pendu.py, ./src/pendu.py...), None if none is """
    full: str | None = located(cwd, path.strip())
    wanted: str | None = shown(full, cwd) if full is not None else None
    return next((artifact for artifact in artifacts if artifact["path"] == wanted), None)
