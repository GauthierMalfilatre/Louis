##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## MCP configuration: the servers the settings declare (mcp.servers) and those of the .mcp.json files (mcp.files), in
## the format of Claude Code, Cursor and Claude Desktop: {"mcpServers": {"<name>": {"command": ..., "args": [...]}}}.
## The servers of a file of the project are only started once the user trusts them
##
from logger.logger import log
from tool.risk import LEVELS
from dataclasses import dataclass, field
import hashlib
import json
import os
import re
import tempfile

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
    # Started with Louis; else only by /mcp restart
    enabled: bool                   = True
    # The tools offered to the model, by their name on the server (globs: "read_*"): all of them without tools
    tools  : list[str] | None       = None
    exclude: list[str]              = field(default_factory=list)
    error  : str | None             = None
    # Declared by a file of the project (a relative path of mcp.files): anyone who wrote in the project may have
    # declared it, it is only started once the user trusts it, as it is written (raw)
    project: bool                   = False
    raw    : dict                   = field(default_factory=dict)

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

def texts(value) -> bool:
    """ Whether the value is a list of texts """
    return isinstance(value, list) and all(isinstance(item, str) for item in value)

def declared(entry, source: str = SETTINGS, project: bool = False) -> Declaration:
    """ A server as an entry declares it: its error says what is wrong with it """
    if not isinstance(entry, dict):
        return Declaration("", source, error="réglage invalide : chaque serveur est un dict {name, command, args, env}",
                           project=project)
    name, command = entry.get("name"), entry.get("command")
    args, env, level = entry.get("args", []), entry.get("env", {}), entry.get("risk")
    enabled, tools, exclude = entry.get("enabled", True), entry.get("tools"), entry.get("exclude", [])
    declaration: Declaration = Declaration(
        name if isinstance(name, str) else "", source, command if isinstance(command, str) else "",
        args if isinstance(args, list) else [], env if isinstance(env, dict) else {}, level if level in LEVELS else None,
        enabled is not False, tools if texts(tools) else None, exclude if texts(exclude) else [],
        project=project, raw=entry
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
    elif not isinstance(enabled, bool):
        declaration.error = "réglage invalide : enabled vaut true ou false"
    elif (tools is not None and not texts(tools)) or not texts(exclude):
        declaration.error = 'réglage invalide : tools et exclude sont des listes de noms d\'outils ("read_*")'
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
    project: bool = not os.path.isabs(full)
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
    return [declared({**entry, "name": name} if isinstance(entry, dict) else entry, path, project)
            for name, entry in servers.items()]

class Trust:
    """
        The servers of the projects the user trusts, in a file outside of any project (a project can not trust
        its own servers): by folder, the fingerprint of each declaration. A server whose declaration changed since
        is not trusted any more
    """
    def __init__(self, path: str | None):
        """ Init the trust kept in the file path; without one, no server of a project is trusted """
        self.__path: str | None = os.path.expanduser(path) if path else None

    @property
    def path(self) -> str | None:
        """ Get the file the trust is kept in """
        return self.__path

    @staticmethod
    def fingerprint(declaration: Declaration) -> str:
        """ What the declaration says, as it is written: a command or an argument changed is another server """
        return hashlib.sha256(json.dumps(declaration.raw, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    @staticmethod
    def folder() -> str:
        """ The project: the folder Louis works in """
        return os.path.realpath(os.getcwd())

    def trusts(self, declaration: Declaration) -> bool:
        """ Whether the server may start: one the project did not declare always may """
        if not declaration.project:
            return True
        return self.__read().get(self.folder(), {}).get(declaration.name) == self.fingerprint(declaration)

    def trust(self, declaration: Declaration) -> None:
        """ Trust the server in this project, as it is declared now. Raises OSError when the file can not be written """
        if self.__path is None:
            raise OSError("no file to keep it in: the setting mcp.trust_file")
        trusted: dict = self.__read()
        trusted.setdefault(self.folder(), {})[declaration.name] = self.fingerprint(declaration)
        folder: str = os.path.dirname(self.__path) or "."
        os.makedirs(folder, exist_ok=True)
        # Written whole, then put in place: a Louis that stops while writing leaves the file as it was
        handle, temporary = tempfile.mkstemp(dir=folder, prefix=".mcp-trusted-")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                json.dump(trusted, file, indent=2, ensure_ascii=False)
            os.replace(temporary, self.__path)
        except OSError:
            os.unlink(temporary)
            raise
        log.info(f"[mcp] {declaration.name}: trusted in {self.folder()}")

    def __read(self) -> dict:
        """ What the file holds: nothing when it does not exist or can not be read """
        if self.__path is None or not os.path.isfile(self.__path):
            return {}
        try:
            with open(self.__path, encoding="utf-8") as file:
                trusted = json.load(file)
        except (OSError, ValueError) as e:
            log.warning(f"[mcp] the trusted servers can not be read in {self.__path}: {e}")
            return {}
        return trusted if isinstance(trusted, dict) else {}

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
