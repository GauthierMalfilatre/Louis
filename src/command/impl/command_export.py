##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /export: write a session, or one of its files, to a file (JSON, Markdown...)
##
from command.command import Command
from command.impl.command_sessions import NOT_SAVED
from config.settings import settings
from events.event_list import EXPORT_DONE
from export.document import build, single
from export.artifacts import find
from export import render_json, render_md, render_html, render_pdf
from logger.logger import log
from session.session import Session
from datetime import datetime
import os

# The formats, by the name typed after /export: each one a module with render(document) (text, or bytes for a PDF)
# and its EXTENSION
FORMATS: dict = {
    "json": render_json,
    "md"  : render_md,
    "html": render_html,
    "pdf" : render_pdf,
}
# Other names typed for a format
ALIASES: dict[str, str] = {"markdown": "md"}

# Typed before the path of a file, to export it alone: last, the path may hold spaces
ARTIFACT: str = "--artifact"

USAGE: str = (f"Usage : /export [{'|'.join(FORMATS)}] [id] [{ARTIFACT} <fichier>], sans id pour la session en cours, "
              f"avec {ARTIFACT} pour un seul des fichiers écrits par Louis.")

def selected(command: Command, app, identifier: str | None, wanted: str | None,
             usage: str) -> tuple[Session, dict, dict | None] | None:
    """
        The session asked for (the current one without identifier), its document, and the file wanted alone if any
        (the document is then that file's). None if there is none: the user was told why, usage on a bad identifier
    """
    session: Session | None = app.session
    if identifier is not None:
        identifier = identifier.removeprefix("#")
        if not identifier.isdigit():
            command.error(app, "usage", usage)
            return None
        if app.user.is_anonymous:
            command.error(app, "anonymous", NOT_SAVED)
            return None
        session = app.user.get_session(int(identifier))
        if session is None:
            command.error(app, "not_found", f"Tu n'as pas de session #{identifier} : tape /sessions pour les voir.",
                          id=int(identifier))
            return None

    document: dict = build(session, app.user)
    if not any(message["role"] == "user" for message in document["messages"]):
        command.error(app, "empty", "Cette session n'a encore aucun message : il n'y a rien à en tirer.")
        return None
    if wanted is None:
        return session, document, None
    artifact: dict | None = find(document["artifacts"], session.cwd, wanted)
    if artifact is None:
        written: str = ", ".join(file["path"] for file in document["artifacts"]) or "aucun"
        command.error(app, "no_artifact", f"Louis n'a pas écrit {wanted} dans cette session. "
                                          f"Fichiers écrits : {written}.", path=wanted)
        return None
    return session, single(document, artifact), artifact

class ExportCommand(Command):
    def __init__(self):
        super().__init__(
            "export",
            description="écrit la session en cours, ou la session <id>, dans un fichier (ou un seul de ses fichiers)",
            usage=f"[{'|'.join(FORMATS)}] [id] [{ARTIFACT} <fichier>]"
        )

    def handle(self, app, arguments: str) -> None:
        """ Write the session asked for in the format asked for (JSON by default), in the export folder """
        #split args
        arguments, flag, wanted = arguments.partition(ARTIFACT)
        wanted = wanted.strip()
        if flag and not wanted:
            self.error(app, "usage", USAGE)
            return
        words: list[str] = arguments.split()
        #get format of export, json if none
        name: str = words.pop(0).lower() if words and not words[0].removeprefix("#").isdigit() else "json"
        name = ALIASES.get(name, name)
        # format do not exsit
        if name not in FORMATS or len(words) > 1:
            self.error(app, "usage", USAGE)
            return

        #get session, document and file asked for
        found = selected(self, app, words[0] if words else None, wanted if flag else None, USAGE)
        if found is None:
            return
        session, document, artifact = found

        renderer = FORMATS[name]
        # An anonymous session has no id: named by the time it is exported, never overwriting another
        stem: str = f"session-{session.id}" if session.saved else f"session-{datetime.now():%Y%m%d-%H%M%S}"
        if artifact is not None:
            # session-12-pendu.py.md: the file, and the session it comes from
            stem += "-" + os.path.basename(artifact["path"])
        folder: str = os.path.abspath(settings.get("export.dir", "exports"))
        path: str = os.path.join(folder, f"{stem}.{renderer.EXTENSION}")
        try:
            output: str | bytes = renderer.render(document)
        except ImportError as e:
            # An optional library of the format is missing (WeasyPrint for the PDF): the message says what to install
            self.error(app, "missing", str(e), format=name)
            return
        try:
            os.makedirs(folder, exist_ok=True)
            if isinstance(output, bytes):
                with open(path, "wb") as file:
                    file.write(output)
            else:
                with open(path, "w", encoding="utf-8") as file:
                    file.write(output)
        except OSError as e:
            self.error(app, "write", f"Impossible d'écrire {path} : {e.strerror or e}", path=path)
            return

        log.info(f"[export] session #{session.id}{f' ({wanted})' if flag else ''} written to {path} ({name})")
        app.events.dispatch(
            EXPORT_DONE, format=name, path=path, id=session.id, messages=len(document["messages"]),
            artifact=artifact["path"] if artifact is not None else None, artifacts=len(document["artifacts"])
        )
