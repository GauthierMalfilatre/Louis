##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Git tool: status, diff, log, branches, commits and pushes of the project
##
from tool.tool import Tool
from utils.path import ROOT, resolve_path
import os
import subprocess

# Nobody can answer a prompt from inside a tool: no password, no editor, no pager, no colors
ENV: dict[str, str] = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_EDITOR": "true", "GIT_PAGER": "cat",
                       "GH_PROMPT_DISABLED": "1", "GH_PAGER": "cat", "NO_COLOR": "1"}

# Where the work is shared: the model commits and pushes on a branch of its own, then opens a pull request
PROTECTED: tuple[str, ...] = ("main", "master", "dev", "develop")

LOG_COUNT = 15
BRANCH_COUNT = 20

REFUSED = "Ne le retente pas : demande-lui ce qu'il veut à la place."

# The git commands small models write instead of the actions of the tool: the action they mean
ALIASES: dict[str, str] = {
    "checkout": "branch", "switch": "branch", "create_branch": "branch", "new_branch": "branch",
    "list_branches": "branches", "fetch": "branches",
    "delete": "delete_branch", "remove_branch": "delete_branch",
}
# The git commands left to the user: they can lose work, or end in conflicts a model can not solve
UNSUPPORTED: tuple[str, ...] = ("merge", "rebase", "reset", "stash", "cherry-pick", "revert", "restore", "clean")

def run(*args: str, timeout: int = 60) -> tuple[bool, str]:
    """ Run git or gh without a shell: what the model writes is never read by bash """
    try:
        res = subprocess.run(args, cwd=ROOT, env=ENV, stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return False, f"{args[0]} n'est pas installé."
    except subprocess.TimeoutExpired:
        return False, f"'{' '.join(args[:3])}' n'a pas répondu en {timeout}s."
    return res.returncode == 0, (res.stdout + res.stderr).strip()

def current_branch() -> str | None:
    """ The branch checked out, None outside a repository or on a detached HEAD """
    ok, out = run("git", "symbolic-ref", "--quiet", "--short", "HEAD")
    return out if ok and out else None

def valid_branch(name) -> bool:
    """ Whether name can be a branch: never an option of git, never a name git would refuse """
    return isinstance(name, str) and bool(name) and not name.startswith("-") \
        and run("git", "check-ref-format", "--branch", name)[0]

def has_ref(ref: str) -> bool:
    """ Whether the ref exists: refs/heads/dev for a branch here, refs/remotes/origin/dev for one of origin """
    return run("git", "rev-parse", "--verify", "--quiet", ref)[0]

def fetch() -> None:
    """ Learn the branches origin has now: offline, the last ones known stay """
    run("git", "fetch", "--quiet", "--prune", "origin", timeout=30)

def empty_repository() -> bool:
    """ Whether the repository has no commit yet, on any branch """
    ok, out = run("git", "rev-list", "-n", "1", "--all")
    return ok and not out

def origin_has(branch: str) -> bool | None:
    """ Whether origin has the branch, asked to origin itself: None if it can not be reached """
    ok, out = run("git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}", timeout=30)
    return bool(out) if ok else None

def unknown_arguments(tool: Tool, arguments: dict) -> str | None:
    """
        Small models invent arguments (force, new...): one that does not exist is refused, for the model never to
        believe it did something
    """
    known: dict = tool.schema["function"]["parameters"]["properties"]
    extra: list[str] = [name for name in arguments if name not in known]
    if not extra:
        return None
    return f"Erreur : {', '.join(extra)} n'existe pas pour {tool.name}. Ses paramètres sont : {', '.join(known)}."

def as_list(value) -> list:
    """ Small models send a single path as a string instead of a list of one """
    if isinstance(value, str):
        return [value] if value else []
    return value if isinstance(value, list) else []

class GitTool(Tool):
    def __init__(self):
        super().__init__(
            "git",
            "Git du projet. status, diff, log : voir l'état, les changements, l'historique. "
            "branches : lister les branches, d'ici et d'origin. branch (comme git checkout ou switch) : passer sur une "
            "branche (d'ici ou d'origin), ou en créer une depuis base. delete_branch : supprimer une branche locale dont le travail est sauf. "
            "pull : récupérer la branche courante. "
            "commit : ajouter des fichiers et les commiter. push : pousser la branche courante sur origin. "
            f"On ne commite ni ne pousse sur {', '.join(PROTECTED)} : crée d'abord une branche. Seule exception : "
            "le premier commit d'un dépôt vide, qui va sur sa branche principale.",
            {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["status", "diff", "log", "branches", "branch", "delete_branch", "pull", "commit",
                                 "push"]
                    },
                    "branch": {
                        "type": "string",
                        "description": "branch, delete_branch, push : nom de la branche, comme feat/git-tool ou fix/login"
                    },
                    "base": {
                        "type": "string",
                        "description": "branch : d'où part une nouvelle branche, comme dev (défaut : la branche courante)"
                    },
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "commit : fichiers à commiter. diff : fichiers à comparer (défaut : tous)"
                    },
                    "message": {
                        "type": "string",
                        "description": "commit : message du commit, qui suit les conventions du projet"
                    }
                },
                "required": ["action"]
            }
        )

    def handle(self, app, **kwargs) -> str:
        """ Run the git action asked for """
        if (unknown := unknown_arguments(self, kwargs)) is not None:
            return unknown
        action = kwargs.get("action")
        if isinstance(action, str):
            action = action.strip().lower()
            if action == "add":
                return "Erreur : pas d'action add, commit ajoute lui-même les fichiers : action commit, avec paths et message."
            if action in ("checkout", "switch") and kwargs.get("paths") and not kwargs.get("branch"):
                return ("Erreur : checkout de fichiers (annuler leurs changements) n'est pas disponible. Pour changer "
                        "de branche : action branch, avec branch.")
            if action in UNSUPPORTED:
                return f"Erreur : {action} n'est pas disponible. Si l'utilisateur le veut, dis-lui de le faire lui-même."
            action = ALIASES.get(action, action)
        if action == "status":
            return self.__read("git", "status", "--short", "--branch")
        if action == "diff":
            files = [resolve_path(app, p) for p in as_list(kwargs.get("paths")) if isinstance(p, str)]
            if None in files:
                return "Erreur : un des fichiers est en dehors du projet."
            return self.__diff(files)
        if action == "log":
            return self.__read("git", "log", "--oneline", "--decorate", f"-{LOG_COUNT}")
        if action == "branches":
            return self.__branches()
        if action == "branch":
            return self.__branch(app, kwargs.get("branch"), kwargs.get("base"))
        if action == "delete_branch":
            return self.__delete_branch(app, kwargs.get("branch"))
        if action == "pull":
            return self.__pull(app)
        if action == "commit":
            return self.__commit(app, as_list(kwargs.get("paths")), kwargs.get("message"))
        if action == "push":
            return self.__push(app, kwargs.get("branch"))
        return ("Erreur : 'action' doit valoir status, diff, log, branches, branch, delete_branch, pull, commit "
                "ou push.")

    @staticmethod
    def __read(*args: str) -> str:
        """ An action that changes nothing: run without asking """
        ok, out = run(*args)
        return f"OK :\n{out or '(rien)'}" if ok else f"Erreur : {out}"

    @staticmethod
    def __diff(files: list[str]) -> str:
        """ The changes since the last commit: git diff leaves the new files out, they are named after it """
        ok, out = run("git", "diff", "HEAD", "--", *files)
        if not ok:
            return f"Erreur : {out}"
        _, new = run("git", "ls-files", "--others", "--exclude-standard", "--", *files)
        if new:
            out += ("\n\n" if out else "") + "Fichiers nouveaux, pas encore suivis par git :\n" + new
        return f"OK :\n{out or '(aucun changement)'}"

    @staticmethod
    def __branches() -> str:
        """ The branches here, then those only origin has: the most recent first """
        fetch()
        # Tab-separated: a branch name can not hold one
        ok, out = run("git", "for-each-ref", "--sort=-committerdate",
                      "--format=%(refname)%09%(upstream:track)%09%(committerdate:relative)",
                      "refs/heads", "refs/remotes/origin")
        if not ok:
            return f"Erreur : {out}"
        current: str | None = current_branch()
        here: list[tuple[str, str]] = []
        there: list[tuple[str, str]] = []
        for line in out.splitlines():
            ref, track, when = line.split("\t")
            if ref.startswith("refs/heads/"):
                name: str = ref.removeprefix("refs/heads/")
                here.append((name, f"{'*' if name == current else ' '} {name}{' ' + track if track else ''} ({when})"))
            elif not ref.endswith("/HEAD"):
                name = ref.removeprefix("refs/remotes/origin/")
                there.append((name, f"  {name} ({when})"))
        names: set[str] = {name for name, _ in here}
        there = [branch for branch in there if branch[0] not in names]

        def shown(branches: list[tuple[str, str]]) -> list[str]:
            more: int = len(branches) - BRANCH_COUNT
            return [line for _, line in branches[:BRANCH_COUNT]] + ([f"  … {more} de plus"] if more > 0 else [])
        lines: list[str] = ["Branches d'ici (* : la branche courante) :", *(shown(here) or ["  aucune"])]
        if there:
            lines += ["Seulement sur origin (branch pour les récupérer) :", *shown(there)]
        return "OK :\n" + "\n".join(lines)

    def __branch(self, app, name, base) -> str:
        """
            Switch to the branch: one from here, or one of origin, followed from here. A new branch starts from base,
            as origin has it when it can: the work of the others, not an old copy of it
        """
        if not valid_branch(name):
            return f"Erreur : '{name}' n'est pas un nom de branche valide."
        if name == current_branch():
            return f"OK : déjà sur {name}."
        if empty_repository():
            return (f"Erreur : le dépôt n'a encore aucun commit, une branche ne peut partir de rien. Fais le premier "
                    f"commit directement sur {current_branch() or 'main'} (action commit), pousse-le (action push), "
                    "puis crée les branches depuis lui.")
        if has_ref(f"refs/heads/{name}"):
            summary, args, done = f"Passage sur la branche {name}", ["switch", name], ""
        else:
            fetch()
            if has_ref(f"refs/remotes/origin/{name}"):
                summary, args, done = (f"Passage sur la branche {name}, récupérée depuis origin",
                                       ["switch", "--track", f"origin/{name}"], " (récupérée depuis origin)")
            else:
                start: str = current_branch() or "HEAD"
                if base:
                    if not valid_branch(base):
                        return f"Erreur : '{base}' n'est pas un nom de branche valide."
                    if has_ref(f"refs/remotes/origin/{base}"):
                        start = f"origin/{base}"
                    elif has_ref(f"refs/heads/{base}"):
                        start = base
                    else:
                        return f"Erreur : la branche '{base}' n'existe pas, ni ici ni sur origin."
                summary, args, done = (f"Création de la branche {name}, depuis {start}",
                                       ["switch", "--no-track", "-c", name, start], f" (nouvelle, depuis {start})")
        if not app.permissions.request(self.name, summary):
            return f"Refusé : l'utilisateur n'a pas autorisé le passage sur '{name}'. {REFUSED}"

        ok, out = run("git", *args)
        if not ok:
            return f"Erreur : git switch a échoué : {out}"
        # The files are those of the other branch now: what the model read of them is out of date
        app.seen_files.clear()
        return f"OK : sur la branche {name}{done}."

    def __delete_branch(self, app, name) -> str:
        """ Delete a branch here, only when its work is safe: merged, or on origin. Origin keeps its own """
        if not valid_branch(name):
            return f"Erreur : '{name}' n'est pas un nom de branche valide."
        if name in PROTECTED:
            return f"Erreur : on ne supprime pas {name}."
        if name == current_branch():
            return f"Erreur : {name} est la branche courante. Passe d'abord sur une autre branche."
        if not has_ref(f"refs/heads/{name}"):
            return f"Erreur : il n'y a pas de branche '{name}' ici."
        _, last = run("git", "log", "-1", "--format=dernier commit : %h %s", f"refs/heads/{name}")
        if not app.permissions.request(self.name, f"Suppression de la branche {name}, ici seulement", last):
            return f"Refusé : l'utilisateur n'a pas autorisé la suppression de '{name}'. {REFUSED}"

        ok, out = run("git", "branch", "-d", name)
        if not ok:
            if "not fully merged" in out:
                return (f"Erreur : {name} a des commits qui ne sont ni fusionnés ni sur origin : elle est gardée, pour "
                        "ne pas perdre ce travail. Seul l'utilisateur peut la forcer, avec git branch -D.")
            return f"Erreur : git branch -d a échoué : {out}"
        return f"OK : branche {name} supprimée ici."

    def __pull(self, app) -> str:
        """ Bring the current branch up to date with origin, only when it needs no merge """
        branch: str | None = current_branch()
        if branch is None:
            return "Erreur : aucune branche n'est active (HEAD détaché, ou pas de dépôt git)."
        if not app.permissions.request(self.name, f"Mise à jour de {branch} depuis origin"):
            return f"Refusé : l'utilisateur n'a pas autorisé le pull. {REFUSED}"
        ok, out = run("git", "pull", "--ff-only", timeout=120)
        if not ok:
            return f"Erreur : git pull a échoué : {out}"
        app.seen_files.clear()
        return f"OK : {branch} est à jour.\n{out}"

    def __commit(self, app, paths: list, message) -> str:
        """ Stage the files and commit them, Louis as co-author: unstaged again if the user refuses """
        if not isinstance(message, str) or not message.strip():
            return "Erreur : 'message' est requis pour commit."
        files = [resolve_path(app, p) for p in paths if isinstance(p, str)]
        if not files or len(files) != len(paths):
            return "Erreur : 'paths' est requis : la liste des fichiers à commiter."
        if None in files:
            return "Erreur : un des fichiers est en dehors du projet."
        branch: str | None = current_branch()
        # The first commit of a repository goes on its main branch: the others will start from it
        if branch in PROTECTED and not empty_repository():
            return f"Erreur : on ne commite pas sur {branch}. Crée d'abord une branche (action branch)."

        ok, out = run("git", "add", "--", *files)
        if not ok:
            return f"Erreur : git add a échoué : {out}"
        # Nothing staged: the files are as in the last commit
        if run("git", "diff", "--cached", "--quiet")[0]:
            return "Erreur : rien à commiter, ces fichiers n'ont pas changé depuis le dernier commit."

        trailer: list[str] = []
        coauthor: str = app.settings.get("git.coauthor") or ""
        if coauthor:
            trailer = ["--trailer", f"Co-authored-by: {coauthor}"]
        _, stat = run("git", "diff", "--cached", "--stat")
        signed: str = f"{message.strip()}\n\nCo-authored-by: {coauthor}" if coauthor else message.strip()
        preview: str = "\n".join(f"  {line}" for line in signed.splitlines()) + f"\n\n{stat}"
        if not app.permissions.request(self.name, f"Commit sur {branch or 'HEAD'}", preview):
            run("git", "reset", "-q", "--", *files)
            return f"Refusé : l'utilisateur n'a pas autorisé ce commit. {REFUSED}"

        ok, out = run("git", "commit", "-m", message.strip(), *trailer)
        if not ok:
            return f"Erreur : git commit a échoué : {out}"
        return f"OK : {out.splitlines()[0]}"

    def __push(self, app, asked) -> str:
        """
            Push the current branch to origin, and track it there. A protected branch only when origin does not have
            it yet: the first push of a new repository
        """
        branch: str | None = current_branch()
        if branch is None:
            return "Erreur : aucune branche n'est active (HEAD détaché, ou pas de dépôt git)."
        if asked and asked != branch:
            return f"Erreur : push pousse la branche courante, {branch}. Passe d'abord sur {asked} (action branch)."
        if empty_repository():
            return "Erreur : rien à pousser, le dépôt n'a encore aucun commit."
        if branch in PROTECTED and origin_has(branch) is not False:
            return f"Erreur : on ne pousse pas sur {branch}. Crée une branche, puis ouvre une pull request."
        ok, count = run("git", "rev-list", "--count", f"origin/{branch}..HEAD")
        if ok and count == "0":
            return f"OK : origin/{branch} est déjà à jour, rien à pousser."
        # The commits no remote has yet: also right for a branch origin does not know
        _, ahead = run("git", "log", "--oneline", "HEAD", "--not", "--remotes")
        if not app.permissions.request(self.name, f"Push de {branch} sur origin", ahead):
            return f"Refusé : l'utilisateur n'a pas autorisé le push. {REFUSED}"
        ok, out = run("git", "push", "-u", "origin", branch, timeout=120)
        if not ok:
            return f"Erreur : git push a échoué : {out}"
        return f"OK : {branch} poussée sur origin."
