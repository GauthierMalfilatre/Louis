##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Knowledge class: the knowledge base of Louis, what the user indexed and the model looks up (RAG)
##
## Usage:  knowledge = Knowledge.from_settings(settings, bus)
##         knowledge.index("~/docs/python", "python")     the folder, cut and embedded (RAG_INDEXED tells how it went)
##         hits = knowledge.search("comment lire un fichier json ?")     (RAG_RETRIEVED tells what was found)
##
from rag.chunker import split
from rag.embedder import Embedder, EmbedError
from rag.index import Index, Hit
from rag.ingest import scan, load
from events.event_bus import EventBus
from events.event_list import RAG_INDEXING, RAG_INDEX_PROGRESS, RAG_INDEXED, RAG_RETRIEVED
from config.settings import settings as default_settings
from logger.logger import log
import os
import re
import time

# Passages embedded in one request, across files: a folder of small files is not one request per file
FLUSH_CHUNKS  : int = 64
# Files between two RAG_INDEX_PROGRESS, whatever they were (a folder already indexed goes by fast)
PROGRESS_EVERY: int = 100

def rag_path() -> str:
    """ Where the index is: LOUIS_RAG, or the file of the settings in the working directory (as louis.db) """
    return os.environ.get("LOUIS_RAG") or os.path.join(os.getcwd(), default_settings["rag.file"])

def source_name(root: str, name: str | None = None) -> str:
    """ The name of a source: the one given, or the name of its folder, cut to what a command can type """
    return re.sub(r"[^\w.-]+", "-", (name or os.path.basename(os.path.normpath(root)) or "root")).strip("-") or "root"

class Knowledge:
    """
        Knowledge Class: indexes folders and searches them. It tells what it does through the bus, never printing.
        Without the embedding model (Ollama stopped, model not downloaded), it goes on by keywords alone
    """
    def __init__(self, bus: EventBus, index: Index, embedder: Embedder | None, results: int = 4):
        """ Init the knowledge base on an index, embedding with embedder (or not at all) """
        self.__bus     : EventBus       = bus
        self.__index   : Index          = index
        self.__embedder: Embedder | None = embedder
        self.__results : int            = results

    @classmethod
    def from_settings(cls, settings: dict[str], bus: EventBus) -> "Knowledge":
        """ The knowledge base the settings describe """
        embedder: Embedder = Embedder(
            settings["chat.uri"],
            settings.get("rag.embed.model", "nomic-embed-text"),
            settings.get("rag.embed.query_prefix", ""),
            settings.get("rag.embed.document_prefix", ""),
            settings.get("rag.embed.batch", 32)
        )
        return cls(bus, Index(rag_path()), embedder, settings.get("rag.results", 4))

    @property
    def empty(self) -> bool:
        """ Check if nothing is indexed: there is nothing to look up """
        return self.__index.empty

    @property
    def results(self) -> int:
        """ Get how many passages a search gives by default """
        return self.__results

    @property
    def path(self) -> str:
        """ Get the file of the index """
        return self.__index.path

    def sources(self) -> list[dict]:
        """ The sources indexed: {name, root, files, chunks, embedded, model, updated_at} """
        return self.__index.sources()

    def forget(self, source: str) -> int:
        """ Remove a source: the passages removed, 0 if it was not there """
        return self.__index.forget(source)

    def search(self, query: str, source: str | None = None, limit: int | None = None) -> list[Hit]:
        """ The passages that answer the query best, in one source or in all of them """
        start: float = time.perf_counter()
        vector: list[float] | None = None
        model: str | None = None
        if self.__embedder is not None:
            try:
                vector, model = self.__embedder.query(query), self.__embedder.model
            except EmbedError as e:
                log.warning(f"[rag] searching by keywords only: {e.message}")
        hits: list[Hit] = self.__index.search(query, vector, model, limit or self.__results, source)
        self.__bus.dispatch(
            RAG_RETRIEVED,
            query=query,
            source=source,
            mode="hybrid" if vector is not None else "keyword",
            hits=[{"source": h.source, "path": h.path, "start": h.start, "end": h.end, "score": h.score} for h in hits],
            duration=round(time.perf_counter() - start, 3)
        )
        return hits

    def index(self, root: str, name: str | None = None) -> dict:
        """
            Index a folder as a source, or bring it up to date: only the files that changed are read again,
            and the ones gone are forgotten. What was done is told to the bus; a Ctrl+C leaves the files
            done so far indexed (each one is saved whole). NOTE: Raisable (OSError, sqlite3.Error)
        """
        start: float = time.perf_counter()
        root = os.path.realpath(root)
        source: str = source_name(root, name)
        paths: list[str] = scan(root)
        self.__bus.dispatch(RAG_INDEXING, source=source, root=root, files=len(paths))

        embedder: Embedder | None = self.__embedder
        self.__index.begin(source, root, embedder.model if embedder else None)
        known: dict[str, tuple[str, bool]] = self.__index.files(source)

        seen: set[str] = set()
        # The files to save, with their passages: embedded together once there are enough of them
        work: list[tuple[str, str, list]] = []
        counts: dict[str, int] = {"updated": 0, "unchanged": 0, "skipped": 0, "chunks": 0, "embedded": 0}
        warning: str | None = None

        def flush() -> None:
            """ Embed the files waiting, and save them """
            nonlocal embedder, warning
            if not work:
                return
            vectors: list[list[float]] | None = None
            if embedder is not None:
                try:
                    vectors = embedder.documents([f"{path}\n{chunk.text}" for path, _, chunks in work for chunk in chunks])
                except EmbedError as e:
                    # The rest of the folder is indexed by keywords: a later /index embeds it (the files are not "embedded")
                    log.warning(f"[rag] not embedding the rest of {source}: {e.message}")
                    embedder, warning = None, e.message
            taken: int = 0
            for path, digest, chunks in work:
                self.__index.put(source, path, digest, chunks, vectors[taken:taken + len(chunks)] if vectors else None)
                taken += len(chunks)
                counts["updated"] += 1
                counts["chunks"] += len(chunks)
                counts["embedded"] += len(chunks) if vectors else 0
            work.clear()

        for number, path in enumerate(paths, 1):
            relative: str = "/" + os.path.relpath(path, root).replace(os.sep, "/")
            loaded: tuple[str, str] | None = load(path)
            chunks = split(loaded[0]) if loaded else []
            if not chunks:
                counts["skipped"] += 1
            else:
                seen.add(relative)
                digest: str = loaded[1]
                before: tuple[str, bool] | None = known.get(relative)
                # Unchanged, unless it lacks the vectors that can be made now
                if before is not None and before[0] == digest and (before[1] or embedder is None):
                    counts["unchanged"] += 1
                else:
                    work.append((relative, digest, chunks))
                    if sum(len(item[2]) for item in work) >= FLUSH_CHUNKS:
                        flush()
            if number % PROGRESS_EVERY == 0:
                self.__bus.dispatch(RAG_INDEX_PROGRESS, source=source, done=number, total=len(paths))
        flush()

        gone: list[str] = [path for path in known if path not in seen]
        for path in gone:
            self.__index.drop(source, path)

        result: dict = {
            "source": source, "root": root, "files": len(seen), **counts, "removed": len(gone), "warning": warning,
            "duration": round(time.perf_counter() - start, 3)
        }
        self.__bus.dispatch(RAG_INDEXED, **result)
        return result
