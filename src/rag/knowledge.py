##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Knowledge class: the knowledge base of Louis, what the user indexed and the model looks up (RAG)
##
## Usage:  knowledge = Knowledge.from_settings(settings, bus)
##         knowledge.index("~/docs/python", "python")     the folder, cut and embedded (RAG_INDEXED tells how it went)
##         found = knowledge.search("comment lire un fichier json ?")     (RAG_RETRIEVED tells what was found)
##
## A search goes in two steps: the index finds what may answer (keywords and meaning, rag/index.py), then the
## reranker reads each of those passages with the question, puts the best first and leaves out the near-misses
## (rag/reranker.py). Without the reranker (turned off, not installed), the order of the index is kept, and nothing is left out.
## A search may be kept to some files, by their path or their kind (code, doc, config, data): the model chooses, from
## what catalog() tells it the base holds.
## A source may ask for its passages of code to be described by the chat model at indexing (/index --describe): the
## description is searched with the passage (rag/describer.py)
##
from dataclasses import dataclass, replace
from rag.chunker import Chunk, split, VERSION
from rag.context import contexts, header, brief
from rag.describer import Describer, DescribeError
from rag.embedder import Embedder, EmbedError
from rag.index import Index, Hit, Filter, path_matches, kind_of
from rag.ingest import scan, load, generated, GENERATED_RATIO
from rag.reranker import Reranker, RerankError
from events.event_bus import EventBus
from events.event_list import RAG_INDEXING, RAG_INDEX_PROGRESS, RAG_INDEXED, RAG_RETRIEVED, RAG_DESCRIBE_PROGRESS
from config.settings import settings as default_settings
from logger.logger import log
import hashlib
import os
import re
import time

# Passages embedded in one request, across files: a folder of small files is not one request per file
FLUSH_CHUNKS  : int = 64
# Files between two RAG_INDEX_PROGRESS, whatever they were (a folder already indexed goes by fast)
PROGRESS_EVERY: int = 100
# Folders of a source told to the model at most, the biggest: each one costs tokens in every request
CATALOG_FOLDERS: int = 20

def rag_path() -> str:
    """ Where the index is: LOUIS_RAG, or the file of the settings in the working directory (as louis.db) """
    return os.environ.get("LOUIS_RAG") or os.path.join(os.getcwd(), default_settings["rag.file"])

def source_name(root: str, name: str | None = None) -> str:
    """ The name of a source: the one given, or the name of its folder, cut to what a command can type """
    return re.sub(r"[^\w.-]+", "-", (name or os.path.basename(os.path.normpath(root)) or "root")).strip("-") or "root"

def passage(path: str, context: str, description: str, text: str, reranked: bool = False) -> str:
    """
        A passage as the embeddings and the reranker read it: where it is, what it does when it was described, its
        text. The reranker reads a shorter context: each character of it is one of the passage less (rag/context.py)
    """
    return "\n".join(part for part in (header(path, brief(context) if reranked else context), description, text) if part)

def describable(path: str) -> bool:
    """ Whether the passages of a file are described: its code only (a document already says what it does in words) """
    return kind_of(path) == "code" and not path.endswith(".ipynb")

@dataclass(frozen=True, slots=True)
class Found:
    """
        What a search gives: the passages, best first, and how many the index found before the reranker left the
        near-misses out. No hit out of some candidates: the base holds nothing that answers, not "try other words".
        files is how many files the filter on the paths and kinds kept (None without one): 0, the filter is wrong
    """
    hits      : list[Hit]
    candidates: int
    files     : int | None = None

class Knowledge:
    """
        Knowledge Class: indexes folders and searches them. It tells what it does through the bus, never printing.
        Without the embedding model (Ollama stopped, model not downloaded), it goes on by keywords alone
    """
    def __init__(self, bus: EventBus, index: Index, embedder: Embedder | None, results: int = 4,
                 reranker: Reranker | None = None, generated_ratio: float = GENERATED_RATIO,
                 describer: Describer | None = None):
        """
            Init the knowledge base on an index, embedding with embedder (or not at all), reranking with reranker (or
            not). A file with fewer distinct lines than generated_ratio is not indexed (0: only the marked ones).
            describer writes what the passages of code do, for the sources that ask for it
        """
        self.__bus      : EventBus          = bus
        self.__index    : Index             = index
        self.__embedder : Embedder | None   = embedder
        self.__results  : int               = results
        self.__reranker : Reranker | None   = reranker
        self.__generated: float             = generated_ratio
        self.__describer: Describer | None  = describer

    @classmethod
    def from_settings(cls, settings: dict[str], bus: EventBus) -> "Knowledge":
        """ The knowledge base the settings describe """
        embedder: Embedder = Embedder(
            settings["chat.uri"],
            settings.get("rag.embed.model", "nomic-embed-text"),
            settings.get("rag.embed.query_prefix", ""),
            settings.get("rag.embed.document_prefix", ""),
            settings.get("rag.embed.batch", 32),
            settings.get("rag.embed.gpu", False)
        )
        reranker: Reranker | None = Reranker(
            settings.get("rag.rerank.model", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"),
            settings.get("rag.rerank.pool", 20),
            settings.get("rag.rerank.min_score", 0.0),
            settings.get("rag.rerank.max_chars", 0)
        ) if settings.get("rag.rerank.enabled", False) else None
        chat: str = f"{settings['chat.model.name']}:{settings['chat.model.parameters']}"
        model: str = settings.get("rag.describe.model") or chat
        describer: Describer = Describer(
            settings["chat.uri"],
            model,
            # The chat model keeps the context of the chat (another one would make Ollama reload it); another model
            # has its own, small: a prompt is one passage and the outline of its file, and the less context, the more
            # of the model fits in the GPU
            settings.get("chat.context", 12288) if model == chat else settings.get("rag.describe.context", 4096),
            settings.get("chat.keepalive", "30m"),
            settings.get("rag.describe.predict", 80)
        )
        return cls(bus, Index(rag_path()), embedder, settings.get("rag.results", 4), reranker,
                   settings.get("rag.index.generated_ratio", GENERATED_RATIO), describer)

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

    def folders(self, source: str) -> list[str]:
        """ The folders of a source, the biggest first: what a filter on the paths may name """
        return [folder for folder, _ in self.__index.outline(source)["folders"]]

    def catalog(self) -> str:
        """
            What the base holds, for the model: one line per source, with its files of each kind and its biggest
            folders. Without it, the model knows neither that a project is indexed, nor which path to filter on
        """
        lines: list[str] = []
        for source in self.sources():
            outline: dict = self.__index.outline(source["name"])
            kinds: str = ", ".join(f"{count} {kind}" for kind, count in outline["kinds"].items())
            shown: list[str] = sorted(folder for folder, _ in outline["folders"][:CATALOG_FOLDERS])
            more: int = len(outline["folders"]) - len(shown)
            lines.append(f"- {source['name']} ({source['files']} fichiers : {kinds}) : dossiers {', '.join(shown)}"
                         + (f", et {more} autres" if more > 0 else ""))
        return "\n".join(lines)

    def search(self, query: str, source: str | None = None, limit: int | None = None, *,
               path: str | None = None, kind: str | None = None, drop: bool = True) -> Found:
        """
            The passages that answer the query best, in one source or in all of them, in the files of a path and of a
            kind only when they are given: limit at most, fewer (or none) when the reranker finds the others do not
            answer. drop=False keeps them, ranked (to measure the threshold)
        """
        start: float = time.perf_counter()
        limit = limit or self.__results
        where: Filter = Filter(source, path or None, frozenset({kind}) if kind else frozenset())
        files: int | None = len(self.__index.matching(where)) if where.on_files else None
        vector: list[float] | None = None
        model: str | None = None
        if self.__embedder is not None:
            try:
                vector, model = self.__embedder.query(query), self.__embedder.model
            except EmbedError as e:
                log.warning(f"[rag] searching by keywords only: {e.message}")
        reranker: Reranker | None = self.__reranker
        # The reranker reads its whole pool whatever the limit: the passages it puts first may be far down the index's list
        candidates: list[Hit] = self.__index.search(query, vector, model, max(limit, reranker.pool) if reranker else limit, where)
        retrieved: float = time.perf_counter()

        hits: list[Hit] = candidates[:limit]
        reranked: bool = False
        dropped: int = 0
        if reranker is not None and candidates:
            try:
                # Where a passage is tells what it is about as much as its text: "auth/login.py › def check_password"
                # for "how users log in"; its description says it in the words of the question
                scores: list[float] = reranker.score(query, [passage(hit.path, hit.context, hit.description, hit.text, True)
                                                             for hit in candidates])
            except RerankError as e:
                log.warning(f"[rag] not reranking: {e.message}")
            else:
                ranked: list[Hit] = sorted(
                    (replace(hit, score=round(score, 4), fused=hit.score) for hit, score in zip(candidates, scores)),
                    key=lambda hit: hit.score, reverse=True
                )
                kept: list[Hit] = [hit for hit in ranked if hit.score >= reranker.min_score] if drop else ranked
                hits, reranked, dropped = kept[:limit], True, len(ranked) - len(kept)

        end: float = time.perf_counter()
        self.__bus.dispatch(
            RAG_RETRIEVED,
            query=query,
            source=source,
            path=where.path,
            kind=kind,
            files=files,
            mode="hybrid" if vector is not None else "keyword",
            reranker=reranker.model if reranked else None,
            candidates=len(candidates),
            dropped=dropped,
            hits=[{"source": h.source, "path": h.path, "start": h.start, "end": h.end, "score": h.score, "fused": h.fused}
                  for h in hits],
            rerank=round(end - retrieved, 3) if reranked else None,
            duration=round(end - start, 3)
        )
        return Found(hits, len(candidates), files)

    def index(self, root: str, name: str | None = None, exclude: list[str] | None = None,
              describe: bool | None = None) -> dict:
        """
            Index a folder as a source, or bring it up to date: only the files that changed are read again,
            and the ones gone are forgotten. What was done is told to the bus; a Ctrl+C leaves the files
            done so far indexed (each one is saved whole). exclude, the patterns of paths left out (see
            rag.index.path_matches), is kept with the source: given, it replaces the patterns it had; None keeps them.
            describe too: whether the chat model describes its passages of code (slow: one request per passage, but
            each description is kept, a passage that did not change is never described again).
            The files made by a program are left out too (rag.ingest.generated), and named in RAG_INDEXED.
            NOTE: Raisable (OSError, sqlite3.Error)
        """
        start: float = time.perf_counter()
        root = os.path.realpath(root)
        source: str = source_name(root, name)
        paths: list[str] = scan(root)
        self.__bus.dispatch(RAG_INDEXING, source=source, root=root, files=len(paths))

        embedder: Embedder | None = self.__embedder
        patterns, described = self.__index.begin(source, root, embedder.model if embedder else None, VERSION, exclude,
                                                 describe, self.__describer.model if self.__describer else None)
        describer: Describer | None = self.__describer if described else None
        known: dict[str, tuple[str, bool]] = self.__index.files(source)

        seen: set[str] = set()
        # The files to save, with their passages, contexts and descriptions: embedded together once there are enough
        work: list[tuple[str, str, list[Chunk], list[str], list[str]]] = []
        counts: dict[str, int] = {"updated": 0, "unchanged": 0, "skipped": 0, "excluded": 0, "chunks": 0, "embedded": 0,
                                  "described": 0, "reused": 0}
        made: list[dict] = []
        warning: str | None = None
        describe_warning: str | None = None
        describing: float = 0.0

        def flush() -> None:
            """ Embed the files waiting, and save them """
            nonlocal embedder, warning
            if not work:
                return
            vectors: list[list[float]] | None = None
            if embedder is not None:
                try:
                    vectors = embedder.documents([passage(path, context, description, chunk.text)
                                                  for path, _, chunks, found, said in work
                                                  for chunk, context, description in zip(chunks, found, said)])
                except EmbedError as e:
                    # The rest of the folder is indexed by keywords: a later /index embeds it (the files are not "embedded")
                    log.warning(f"[rag] not embedding the rest of {source}: {e.message}")
                    embedder, warning = None, e.message
            taken: int = 0
            for path, digest, chunks, found, said in work:
                self.__index.put(source, path, digest, chunks, vectors[taken:taken + len(chunks)] if vectors else None,
                                 found, said)
                taken += len(chunks)
                counts["updated"] += 1
                counts["chunks"] += len(chunks)
                counts["embedded"] += len(chunks) if vectors else 0
            work.clear()

        def describe_file(path: str, chunks: list[Chunk], found: list[str]) -> tuple[list[str], bool]:
            """
                What each passage of a file does: from the cache, or asked to the chat model (the file's requests in a
                row). And whether all of them are: a file left short (the model stopped answering) is read again by the
                next /index, its passages already described coming from the cache
            """
            nonlocal describer, describe_warning, describing
            if not described or not describable(path):
                return [""] * len(chunks), True
            # What every request of the file starts with, after the instructions: Ollama reads it once for all of them
            outline: str = "\n".join(dict.fromkeys(f"- {brief(context)}" for context in found if context))
            said: list[str] = []
            asked: int = 0
            for chunk, context in zip(chunks, found):
                key: str = hashlib.sha1(f"{describer.model}\n{path}\n{context}\n{chunk.text}".encode("utf-8")).hexdigest()
                description: str | None = self.__index.described(key)
                if description is not None:
                    counts["reused"] += 1
                elif describer is not None:
                    began: float = time.perf_counter()
                    try:
                        description = describer.describe(path, outline, (chunk.start, chunk.end), brief(context), chunk.text)
                    except DescribeError as e:
                        # The rest is indexed without descriptions: a later /index writes them (nothing is kept of them)
                        log.warning(f"[rag] not describing the rest of {source}: {e.message}")
                        describer, describe_warning = None, e.message
                    describing += time.perf_counter() - began
                    if description:
                        self.__index.remember(source, key, description)
                        counts["described"] += 1
                        asked += 1
                said.append(description or "")
            if asked:
                self.__bus.dispatch(RAG_DESCRIBE_PROGRESS, source=source, path=path, described=counts["described"],
                                    reused=counts["reused"], seconds=round(describing, 1))
            return said, all(said)

        for number, path in enumerate(paths, 1):
            relative: str = "/" + os.path.relpath(path, root).replace(os.sep, "/")
            # Not read at all: what was indexed of it before is forgotten with the files gone
            if any(path_matches(relative, pattern) for pattern in patterns):
                counts["excluded"] += 1
                continue
            loaded: tuple[str, str] | None = load(path)
            reason: str | None = generated(loaded[0], self.__generated) if loaded else None
            if reason is not None:
                made.append({"path": relative, "reason": reason})
                loaded = None
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
                    found: list[str] = contexts(relative, loaded[0], chunks)
                    said, whole = describe_file(relative, chunks, found)
                    # Saved without its hash when some of its passages lack their description: the next /index reads it
                    # again, as a file without its vectors (what was described is in the cache)
                    work.append((relative, digest if whole else "", chunks, found, said))
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
            "exclude": patterns, "generated": made, "describe": described, "describe_warning": describe_warning,
            "describe_seconds": round(describing, 1), "duration": round(time.perf_counter() - start, 3)
        }
        self.__bus.dispatch(RAG_INDEXED, **result)
        return result
