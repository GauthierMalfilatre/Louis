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
from export.document import build, selection
from export.artifacts import select
from export import render_json, render_md, render_html, render_pdf
from logger.logger import log
from session.session import Session
from datetime import datetime
import os
import shlex

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

# Typed last, before the files to export alone: paths, folders or globs, between quotes if they hold spaces
ARTIFACT: str = "--artifact"

# What the files of --artifact can be, for the usage of /export and /share
FILES_HELP: str = (f"avec {ARTIFACT} pour seulement des fichiers écrits par Louis : des chemins, des dossiers (src/) "
                   "ou des motifs (*.py), entre guillemets s'ils ont des espaces, tous s'il n'y en a pas")

USAGE: str = (f"Usage : /export [{'|'.join(FORMATS)}] [id] [{ARTIFACT} [fichiers]], sans id pour la session en cours, "
              f"{FILES_HELP}.")

# Files named in the name of an export of some files: more, they are counted
NAMED_FILES: int = 3

def files_typed(arguments: str) -> tuple[str, list[str] | None]:
    """
        The arguments before --artifact, and the files typed after it: None without --artifact, [] for all of them.
        Raise ValueError on a quote left open
    """
    before, flag, after = arguments.partition(ARTIFACT)
    return before, shlex.split(after) if flag else None

def selected(command: Command, app, identifier: str | None, wanted: list[str] | None,
             usage: str) -> tuple[Session, dict, list[dict] | None] | None:
    """
        The session asked for (the current one without identifier), its document, and the files wanted alone if any
        ([] for all of them: the document is then theirs). None if there is none: the user was told why
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
    if not document["artifacts"]:
        command.error(app, "no_artifact", "Louis n'a écrit aucun fichier dans cette session.")
        return None
    files, unmatched = select(document["artifacts"], session.cwd, wanted) if wanted else (document["artifacts"], [])
    if unmatched:
        written: str = ", ".join(file["path"] for file in document["artifacts"])
        command.error(app, "no_artifact", f"Louis n'a écrit aucun fichier qui corresponde à {', '.join(unmatched)} "
                                          f"dans cette session. Fichiers écrits : {written}.", paths=unmatched)
        return None
    return session, selection(document, files), files

class ExportCommand(Command):
    def __init__(self):
        super().__init__(
            "export",
            description="écrit la session en cours, ou la session <id>, dans un fichier (ou seulement ses fichiers)",
            usage=f"[{'|'.join(FORMATS)}] [id] [{ARTIFACT} [fichiers]]"
        )

    def handle(self, app, arguments: str) -> None:
        """ Write the session asked for in the format asked for (JSON by default), in the export folder """
        #split args
        try:
            arguments, wanted = files_typed(arguments)
        except ValueError:
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
        found = selected(self, app, words[0] if words else None, wanted, USAGE)
        if found is None:
            return
        session, document, files = found

        renderer = FORMATS[name]
        # An anonymous session has no id: named by the time it is exported, never overwriting another
        stem: str = f"session-{session.id}" if session.saved else f"session-{datetime.now():%Y%m%d-%H%M%S}"
        if files is not None:
            # session-12-pendu.py.md: the files, and the session they come from, so that two choices never overwrite
            # each other. Past NAMED_FILES of them: session-12-5-fichiers.md
            names: list[str] = [os.path.basename(file["path"]) for file in files]
            stem += "-" + ("_".join(names) if len(names) <= NAMED_FILES else f"{len(names)}-fichiers")
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

        paths: list[str] | None = [file["path"] for file in files] if files is not None else None
        log.info(f"[export] session #{session.id}{f' ({", ".join(paths)})' if paths else ''} written to {path} ({name})")
        app.events.dispatch(
            EXPORT_DONE, format=name, path=path, id=session.id, messages=len(document["messages"]),
            files=paths, artifacts=len(document["artifacts"])
        )
