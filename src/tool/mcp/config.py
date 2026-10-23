##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## MCP configuration: the servers the settings declare (mcp.servers) and those of the .mcp.json files (mcp.files), in
## the format of Claude Code, Cursor and Claude Desktop: {"mcpServers": {"<name>": {"command": ..., "args": [...]}}}
##
from logger.logger import log
from tool.risk import LEVELS
from dataclasses import dataclass, field
import json
import os
import re

# A variable of the environment of Louis in a declaration: ${GITHUB_TOKEN}, or ${PORT:-8080} with a default
VARIABLE: re.Pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")

SETTINGS: str = "settings"

@dataclass
class Declaration:
    """ A server as it is declared: what is wrong with the declaration is its error """
    name   : str
    source : str                    = SETTINGS
    command: str                    = ""
    args   : list[str]              = field(default_factory=list)
    env    : dict[str, str]         = field(default_factory=dict)
    level  : str | None             = None
    error  : str | None             = None

def expand(value: str) -> str:
    """ The text with the variables it names replaced by their value. Raises KeyError for one that has none """
    def variable(match: re.Match) -> str:
        name, default = match.group(1), match.group(2)
        if name in os.environ:
            return os.environ[name]
        if default is not None:
            return default
        raise KeyError(name)
    return VARIABLE.sub(variable, value)

def declared(entry, source: str = SETTINGS) -> Declaration:
    """ A server as an entry declares it: its error says what is wrong with it """
    if not isinstance(entry, dict):
        return Declaration("", source, error="réglage invalide : chaque serveur est un dict {name, command, args, env}")
    name, command = entry.get("name"), entry.get("command")
    args, env, level = entry.get("args", []), entry.get("env", {}), entry.get("risk")
    declaration: Declaration = Declaration(
        name if isinstance(name, str) else "", source, command if isinstance(command, str) else "",
        args if isinstance(args, list) else [], env if isinstance(env, dict) else {}, level if level in LEVELS else None
    )
    if not declaration.name.strip():
        declaration.error = "réglage invalide : il lui faut un nom (name)"
    elif not declaration.command.strip():
        declaration.error = "réglage invalide : il lui faut une commande à lancer (command)"
    elif not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        declaration.error = "réglage invalide : args est une liste de textes"
    elif not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        declaration.error = "réglage invalide : env est un dict de textes"
    elif level is not None and level not in LEVELS:
        declaration.error = f"réglage invalide : risk vaut {', '.join(LEVELS)}"
    if declaration.error is not None:
        return declaration
    # What the environment gives: a token is named in the file, never written in it
    try:
        declaration.command = expand(declaration.command)
        declaration.args = [expand(arg) for arg in declaration.args]
        declaration.env = {key: expand(value) for key, value in declaration.env.items()}
    except KeyError as e:
        declaration.error = f"la variable {e.args[0]} n'est pas définie (ni de valeur par défaut : ${{{e.args[0]}:-…}})"
    return declaration

def read(path: str) -> list[Declaration]:
    """
        The servers of a .mcp.json file, none if it does not exist. A file that can not be read is a server that
        failed, named after it: /mcp shows why
    """
    full: str = os.path.expanduser(path)
    if not os.path.isfile(full):
        return []
    try:
        with open(full, encoding="utf-8") as file:
            content = json.load(file)
    except json.JSONDecodeError as e:
        return [Declaration(path, path, error=f"fichier JSON invalide (ligne {e.lineno}) : {e.msg}")]
    except (OSError, UnicodeDecodeError) as e:
        return [Declaration(path, path, error=f"fichier illisible : {getattr(e, 'strerror', None) or e}")]
    servers = content.get("mcpServers") if isinstance(content, dict) else None
    if not isinstance(servers, dict):
        return [Declaration(path, path, error='réglage invalide : le fichier a la forme {"mcpServers": {"<nom>": {...}}}')]
    return [declared({**entry, "name": name} if isinstance(entry, dict) else entry, path) for name, entry in servers.items()]

def declarations(settings: dict) -> list[Declaration]:
    """
        Every server declared: those of the settings, then those of each file of mcp.files, in their order. A server
        of a file replaces the one of the same name declared before it (the project after the user); two of the same
        name in one place are an error
    """
    found: list[Declaration] = []
    for source, entries in [(SETTINGS, [declared(entry) for entry in settings.get("mcp.servers") or []]),
                            *[(path, read(path)) for path in settings.get("mcp.files") or []]]:
        names: set[str] = set()
        for declaration in entries:
            if declaration.name in names and declaration.error is None:
                declaration.error = f"réglage invalide : un autre serveur s'appelle déjà {declaration.name}"
            names.add(declaration.name)
            before: Declaration | None = next((known for known in found if known.name == declaration.name
                                               and known.source != source), None)
            if before is not None and declaration.name:
                log.info(f"[mcp] {declaration.name}: declared in {source}, in place of {before.source}")
                found.remove(before)
            found.append(declaration)
    return found
