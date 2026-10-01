##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Pull request tool: list, read, open, comment and merge the pull requests of the project, through gh
##
from tool.tool import Tool
from tool.impl.git.tool_git import run, current_branch, has_ref, PROTECTED, REFUSED
import json

LIST_COUNT = 15
METHODS: tuple[str, ...] = ("merge", "squash", "rebase")
LIST_FIELDS = "number,title,author,isDraft,baseRefName,headRefName"
VIEW_FIELDS = "number,title,state,isDraft,author,baseRefName,headRefName,url,body,reviewDecision,mergeable," \
              "statusCheckRollup"

def pr_number(value) -> int | None:
    """ The number of a pull request: small models send it as "36" or "#36" too """
    text: str = str(value).strip().lstrip("#")
    return int(text) if text.isdigit() else None

def gh_json(*args: str) -> tuple[bool, object]:
    """ Run gh, and read its JSON: the text of the error if it fails """
    ok, out = run("gh", *args)
    if not ok:
        return False, out
    try:
        return True, json.loads(out)
    except ValueError:
        return False, f"réponse illisible de gh : {out[:200]}"

def indented(text: str) -> str:
    """ A text shown with a permission: indented, so its "- " lines are not taken for removed lines of a diff """
    return "\n".join(f"  {line}" for line in text.splitlines())

def checks(rollup: list[dict]) -> str:
    """ The checks of a pull request on one line: a CI job has a conclusion, a commit status a state """
    done: list[str] = []
    for check in rollup or []:
        name: str = check.get("name") or check.get("context") or "?"
        done.append(f"{name} {check.get('conclusion') or check.get('state') or check.get('status') or '?'}")
    return ", ".join(done) or "aucun"

class PullRequestTool(Tool):
    def __init__(self):
        super().__init__(
            "github_pr",
            "Pull requests GitHub du projet, par gh. list : celles qui sont ouvertes. view : le détail d'une PR "
            "(défaut : celle de la branche courante). create : ouvrir une PR de la branche courante, déjà poussée "
            "avec git push. comment : commenter une PR. merge : fusionner une PR.",
            {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "view", "create", "comment", "merge"]
                    },
                    "number": {
                        "type": "integer",
                        "description": "view, comment, merge : numéro de la PR"
                    },
                    "title": {
                        "type": "string",
                        "description": "create : titre de la PR"
                    },
                    "body": {
                        "type": "string",
                        "description": "create : description de la PR. comment : texte du commentaire"
                    },
                    "base": {
                        "type": "string",
                        "description": "create : branche visée (défaut : dev si elle existe, sinon la branche principale)"
                    },
                    "method": {
                        "type": "string",
                        "enum": list(METHODS),
                        "description": "merge : façon de fusionner (défaut : merge)"
                    }
                },
                "required": ["action"]
            }
        )

    def handle(self, app, **kwargs) -> str:
        """ Run the pull request action asked for """
        action = kwargs.get("action")
        if action == "list":
            return self.__list()
        if action == "view":
            return self.__view(kwargs.get("number"))
        if action == "create":
            return self.__create(app, kwargs.get("title"), kwargs.get("body"), kwargs.get("base"))
        if action == "comment":
            return self.__comment(app, kwargs.get("number"), kwargs.get("body"))
        if action == "merge":
            return self.__merge(app, kwargs.get("number"), kwargs.get("method") or "merge")
        return "Erreur : 'action' doit valoir list, view, create, comment ou merge."

    @staticmethod
    def __list() -> str:
        """ The open pull requests, one per line """
        ok, prs = gh_json("pr", "list", "--json", LIST_FIELDS, "--limit", str(LIST_COUNT))
        if not ok:
            return f"Erreur : {prs}"
        if not prs:
            return "OK : aucune pull request ouverte."
        lines: list[str] = [
            f"#{pr['number']} {pr['headRefName']} → {pr['baseRefName']} : {pr['title']} "
            f"({(pr.get('author') or {}).get('login', '?')}{', brouillon' if pr.get('isDraft') else ''})"
            for pr in prs
        ]
        return "OK :\n" + "\n".join(lines)

    @staticmethod
    def __view(number) -> str:
        """ A pull request: where it goes, its review, its checks and its description """
        target: list[str] = []
        if number is not None:
            if pr_number(number) is None:
                return f"Erreur : '{number}' n'est pas un numéro de PR."
            target = [str(pr_number(number))]
        ok, pr = gh_json("pr", "view", *target, "--json", VIEW_FIELDS)
        if not ok:
            return f"Erreur : {pr}"
        return (
            f"OK : #{pr['number']} {pr['title']} [{pr['state']}{', brouillon' if pr.get('isDraft') else ''}]\n"
            f"{pr['headRefName']} → {pr['baseRefName']}, par {(pr.get('author') or {}).get('login', '?')}\n"
            f"{pr['url']}\n"
            f"Review : {pr.get('reviewDecision') or 'aucune'} | Fusionnable : {pr.get('mergeable') or '?'}\n"
            f"Checks : {checks(pr.get('statusCheckRollup'))}\n"
            f"Description :\n{pr.get('body') or '(vide)'}"
        )

    def __create(self, app, title, body, base) -> str:
        """ Open a pull request of the current branch, once it is on origin with all its commits """
        if not isinstance(title, str) or not title.strip():
            return "Erreur : 'title' est requis pour create."
        body = body if isinstance(body, str) else ""
        head: str | None = current_branch()
        if head is None:
            return "Erreur : aucune branche n'est active (HEAD détaché, ou pas de dépôt git)."
        if head in PROTECTED:
            return f"Erreur : on n'ouvre pas de PR depuis {head}. Crée une branche, commite et pousse dessus."
        ok, count = run("git", "rev-list", "--count", f"origin/{head}..HEAD")
        if not ok:
            return f"Erreur : {head} n'est pas sur origin. Pousse-la d'abord (git, action push)."
        if count != "0":
            return f"Erreur : {count} commit(s) de {head} ne sont pas sur origin. Pousse-les d'abord (git, action push)."
        if not base and head != "dev" and has_ref("refs/remotes/origin/dev"):
            base = "dev"
        if base is not None and (not isinstance(base, str) or base.startswith("-")):
            return f"Erreur : '{base}' n'est pas une branche valide."

        into: str = base or "la branche principale"
        preview: str = indented(f"{title.strip()}\n\n{body}".rstrip())
        if not app.permissions.request(self.name, f"Pull request de {head} vers {into}", preview):
            return f"Refusé : l'utilisateur n'a pas autorisé cette pull request. {REFUSED}"
        args: list[str] = ["pr", "create", "--head", head, "--title", title.strip(), "--body", body]
        ok, out = run("gh", *args, *(["--base", base] if base else []), timeout=120)
        if not ok:
            return f"Erreur : gh pr create a échoué : {out}"
        return f"OK : pull request ouverte : {out.splitlines()[-1]}"

    def __comment(self, app, number, body) -> str:
        """ Comment on a pull request """
        if pr_number(number) is None:
            return "Erreur : 'number' est requis pour comment : le numéro de la PR."
        if not isinstance(body, str) or not body.strip():
            return "Erreur : 'body' est requis pour comment : le texte du commentaire."
        if not app.permissions.request(self.name, f"Commentaire sur la PR #{pr_number(number)}", indented(body)):
            return f"Refusé : l'utilisateur n'a pas autorisé ce commentaire. {REFUSED}"
        ok, out = run("gh", "pr", "comment", str(pr_number(number)), "--body", body, timeout=120)
        if not ok:
            return f"Erreur : gh pr comment a échoué : {out}"
        return f"OK : commentaire publié : {out.splitlines()[-1] if out else ''}"

    def __merge(self, app, number, method) -> str:
        """ Merge a pull request, after the user has seen its review and its checks """
        if pr_number(number) is None:
            return "Erreur : 'number' est requis pour merge : le numéro de la PR."
        if method not in METHODS:
            return f"Erreur : 'method' doit valoir {', '.join(METHODS)}."
        ok, pr = gh_json("pr", "view", str(pr_number(number)), "--json", VIEW_FIELDS)
        if not ok:
            return f"Erreur : {pr}"
        if pr["state"] != "OPEN":
            return f"Erreur : la PR #{pr['number']} n'est pas ouverte ({pr['state']})."

        preview: str = indented(
            f"{pr['title']}\n{pr['headRefName']} → {pr['baseRefName']}\n"
            f"Review : {pr.get('reviewDecision') or 'aucune'}\nChecks : {checks(pr.get('statusCheckRollup'))}"
        )
        if not app.permissions.request(self.name, f"Fusion ({method}) de la PR #{pr['number']}", preview):
            return f"Refusé : l'utilisateur n'a pas autorisé cette fusion. {REFUSED}"
        ok, out = run("gh", "pr", "merge", str(pr["number"]), f"--{method}", timeout=120)
        if not ok:
            return f"Erreur : gh pr merge a échoué : {out}"
        return f"OK : PR #{pr['number']} fusionnée dans {pr['baseRefName']}."
