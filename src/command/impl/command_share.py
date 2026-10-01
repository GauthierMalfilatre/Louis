##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /share: publish a session, or one of its files, by a public link the user confirms first
##
from command.command import Command
from command.impl.command_export import selected, ARTIFACT
from events.event_list import SHARE_CREATED
from logger.logger import log
from share.store import create, masked, url

USAGE: str = (f"Usage : /share [id] [{ARTIFACT} <fichier>], sans id pour la session en cours, "
              f"avec {ARTIFACT} pour un seul des fichiers écrits par Louis.")

ANONYMOUS: str = ("Les liens sont gardés avec tes sessions : lance louis avec --user <nom> pour en partager une.")

def files_read(document: dict) -> list[str]:
    """ The files the model read in the session: their content is in the page, with the results of its calls """
    read: list[str] = []
    for message in document["messages"]:
        for call in message.get("tools", []):
            path = (call.get("arguments") or {}).get("path")
            if call["name"] == "cat_file" and call.get("ok") and isinstance(path, str) and path not in read:
                read.append(path)
    return read

def preview(document: dict, hidden: int) -> str:
    """ What the link will show, for the user to know before it is public: no line starts with + or - (a diff) """
    files: list[str] = [file["path"] for file in document["artifacts"]]
    lines: list[str] = [f"  Titre   : {document['title'] or '(sans titre)'}"]
    if document["kind"] == "session":
        count: int = len(document["messages"])
        lines.append(f"  Contenu : {count} message{'s' if count > 1 else ''}, "
                     f"{len(files)} fichier{'s' if len(files) > 1 else ''} écrit{'s' if len(files) > 1 else ''}"
                     f"{f' ({', '.join(files)})' if files else ''}")
        read: list[str] = files_read(document)
        if read:
            lines.append(f"  Lus     : {', '.join(read)} (leur contenu sera visible)")
    if hidden:
        lines.append(f"  Masqué  : {hidden} texte{'s' if hidden > 1 else ''} avec des données sensibles (clés, mots de "
                     "passe, emails...), remplacées par leur type")
    lines.append("  Toute personne qui a le lien pourra le lire, sans compte. /unshare pour le fermer.")
    return "\n".join(lines)

class ShareCommand(Command):
    def __init__(self):
        super().__init__(
            "share",
            description="publie la session en cours, ou la session <id>, par un lien public (ou un seul de ses fichiers)",
            usage=f"[id] [{ARTIFACT} <fichier>]"
        )

    def handle(self, app, arguments: str) -> None:
        """ Publish the session asked for (the current one by default), its sensitive data masked, once confirmed """
        if app.user.is_anonymous:
            self.error(app, "anonymous", ANONYMOUS)
            return
        arguments, flag, wanted = arguments.partition(ARTIFACT)
        wanted = wanted.strip()
        words: list[str] = arguments.split()
        if (flag and not wanted) or len(words) > 1:
            self.error(app, "usage", USAGE)
            return
        found = selected(self, app, words[0] if words else None, wanted if flag else None, USAGE)
        if found is None:
            return
        session, document, artifact = found

        # A public page never shows what the log would mask: with the guard or not
        document, hidden = masked(document)
        what: str = (f"{artifact['path']} (session #{session.id})" if artifact is not None
                     else f"la session #{session.id}")
        if not app.permissions.request("share", f"Publier {what} par un lien public ?", preview(document, hidden),
                                       every_time=True):
            self.error(app, "refused", "Partage annulé : aucun lien n'a été créé.")
            return

        token: str = create(app.user.db, app.user.id, session.id, document)
        log.info(f"[share] {document['kind']} of session #{session.id} shared ({token[:6]}…, {hidden} texts masked)")
        app.events.dispatch(
            SHARE_CREATED, token=token, url=url(token), kind=document["kind"], id=session.id,
            title=document["title"], masked=hidden
        )
