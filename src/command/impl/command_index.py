##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /index and /unindex: choose what the knowledge base holds
##
from command.command import Command
from events.event_list import RAG_SOURCES, RAG_FORGOTTEN
from rag.knowledge import source_name
import os
import shlex

class IndexCommand(Command):
    def __init__(self):
        super().__init__(
            "index",
            description="indexe un dossier de documentation ou de code dans la base de connaissances (sans argument : "
                        "les sources). --exclude laisse de côté des fichiers, et le reste aux /index suivants "
                        "(--exclude \"\" n'exclut plus rien)",
            usage="[<dossier> [<nom>] [--exclude <motif>]...]"
        )

    def handle(self, app, arguments: str) -> None:
        """ List the sources of the knowledge base, or index a folder as one: it is brought up to date if it is one """
        knowledge = app.knowledge
        if knowledge is None:
            self.error(app, "disabled", "La base de connaissances est coupée (réglage rag.enabled).")
            return
        try:
            tokens: list[str] = shlex.split(arguments)
        except ValueError:
            self.error(app, "usage", "Usage : /index [<dossier> [<nom>]] (guillemets non fermés).")
            return
        words: list[str] = []
        # None: the patterns the source already has are kept. Given, they replace them ("" alone: none any more)
        exclude: list[str] | None = None
        rest = iter(tokens)
        for token in rest:
            if token == "--exclude" or token.startswith("--exclude="):
                pattern: str | None = token.partition("=")[2] if "=" in token else next(rest, None)
                if pattern is None:
                    self.error(app, "usage", "Usage : --exclude <motif>, par exemple --exclude \"config/*_grid.yml\".")
                    return
                exclude = [*(exclude or []), pattern]
            else:
                words.append(token)
        if not words:
            if exclude is not None:
                self.error(app, "usage", "Usage : /index <dossier> [<nom>] --exclude <motif> : le dossier d'abord.")
                return
            app.events.dispatch(RAG_SOURCES, sources=knowledge.sources())
            return
        if len(words) > 2:
            self.error(app, "usage", "Usage : /index <dossier> [<nom>] (entoure d'apostrophes un nom avec des espaces).")
            return
        # Any folder of the machine, not only the project: the user chooses what the model may look up
        folder: str = os.path.realpath(os.path.expanduser(words[0]))
        if not os.path.isdir(folder):
            self.error(app, "not_found", f"{words[0]} n'est pas un dossier.", path=words[0])
            return
        name: str = source_name(folder, words[1] if len(words) > 1 else None)
        # Everything it tells (start, progress, end) goes through RAG_INDEXING, RAG_INDEX_PROGRESS and RAG_INDEXED
        knowledge.index(folder, name, exclude)
        # The model can look it up from now on, without restarting
        app.offer_knowledge()

class UnindexCommand(Command):
    def __init__(self):
        super().__init__("unindex", description="retire une source de la base de connaissances", usage="<nom>")

    def handle(self, app, arguments: str) -> None:
        """ Forget a source: its passages are removed from the index, its folder is left alone """
        knowledge = app.knowledge
        name: str = arguments.strip()
        if knowledge is None or not name:
            self.error(app, "usage", "Usage : /unindex <nom>, avec un nom donné par /index.")
            return
        if name not in [source["name"] for source in knowledge.sources()]:
            self.error(app, "not_found", f"Il n'y a pas de source « {name} » : tape /index pour les voir.", source=name)
            return
        app.events.dispatch(RAG_FORGOTTEN, source=name, chunks=knowledge.forget(name))
        app.offer_knowledge()
