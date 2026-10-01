##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /export: write a session to a file (JSON, Markdown...)
##
from command.command import Command
from command.impl.command_sessions import NOT_SAVED
from config.settings import settings
from events.event_list import EXPORT_DONE
from export.document import build, single
from export.artifacts import find
from export import render_json, render_md
from logger.logger import log
from datetime import datetime
import os

# The formats, by the name typed after /export: each one a module with render(document) and its EXTENSION
FORMATS: dict = {
    "json": render_json,
    "md"  : render_md,
}
# Other names typed for a format
ALIASES: dict[str, str] = {"markdown": "md"}

# Typed before the path of a file, to export it alone: last, the path may hold spaces
ARTIFACT: str = "--artifact"

USAGE: str = (f"Usage : /export [{'|'.join(FORMATS)}] [id] [{ARTIFACT} <fichier>], sans id pour la session en cours, "
              f"avec {ARTIFACT} pour un seul des fichiers écrits par Louis.")

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

        #get session
        session = app.session
        #check asked id session
        if words:
            identifier: str = words[0].removeprefix("#")
            if not identifier.isdigit():
                self.error(app, "usage", USAGE)
                return
            if app.user.is_anonymous:
                self.error(app, "anonymous", NOT_SAVED)
                return
            session = app.user.get_session(int(identifier))
            if session is None:
                self.error(app, "not_found", f"Tu n'as pas de session #{identifier} : tape /sessions pour les voir.",
                           id=int(identifier))
                return

        document: dict = build(session, app.user)
        if not any(message["role"] == "user" for message in document["messages"]):
            self.error(app, "empty", "Rien à exporter : cette session n'a encore aucun message.")
            return

        renderer = FORMATS[name]
        # An anonymous session has no id: named by the time it is exported, never overwriting another
        stem: str = f"session-{session.id}" if session.saved else f"session-{datetime.now():%Y%m%d-%H%M%S}"
        if flag:
            artifact: dict | None = find(document["artifacts"], session.cwd, wanted)
            if artifact is None:
                written: str = ", ".join(file["path"] for file in document["artifacts"]) or "aucun"
                self.error(app, "no_artifact", f"Louis n'a pas écrit {wanted} dans cette session. "
                                               f"Fichiers écrits : {written}.", path=wanted)
                return
            document = single(document, artifact)
            # session-12-pendu.py.md: the file, and the session it comes from
            stem += "-" + os.path.basename(artifact["path"])
        folder: str = os.path.abspath(settings.get("export.dir", "exports"))
        path: str = os.path.join(folder, f"{stem}.{renderer.EXTENSION}")
        try:
            os.makedirs(folder, exist_ok=True)
            with open(path, "w", encoding="utf-8") as file:
                file.write(renderer.render(document))
        except OSError as e:
            self.error(app, "write", f"Impossible d'écrire {path} : {e.strerror or e}", path=path)
            return

        log.info(f"[export] session #{session.id}{f' ({wanted})' if flag else ''} written to {path} ({name})")
        app.events.dispatch(
            EXPORT_DONE, format=name, path=path, id=session.id, messages=len(document["messages"]),
            artifact=document["artifacts"][0]["path"] if flag else None, artifacts=len(document["artifacts"])
        )
