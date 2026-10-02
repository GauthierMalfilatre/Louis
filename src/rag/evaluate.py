##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Evaluate the search of the knowledge base on questions whose answer is known, without the model:
##   cd src && python -m rag.evaluate ../docs/rag_eval.json [--save before.json] [--baseline before.json]
##
## Each question says which passages answer it (a path from the root of the source, and the lines when they matter).
## The search runs as search_knowledge runs it (k passages), then deeper, to see the rank of the answer when it is
## not in the k. A question with no expected passage is one the source cannot answer: whatever comes back is noise,
## and its scores tell how high a near-miss scores, next to the scores of the right answers (where a threshold goes).
## The scores of the fusion (RRF) only tell a rank: they are worth comparing once a reranker gives them.
## The deeper search keeps what the threshold of the reranker drops: the scores of the right answers it would drop
## are seen, and the table of thresholds tells what each one would keep and drop.
## Compare:  --no-rerank (the index alone), --rerank-model Xenova/ms-marco-MiniLM-L-6-v2, --min-score 0.2
## A question may give the filters the model should choose ("filters": {"path": "src/auth", "kind": "code"}):
## the run then tells what the filters bring when they are well chosen (--no-filters: without them, to compare)
##
from dataclasses import dataclass, asdict
from datetime import datetime
from events.event import Event
from events.event_bus import EventBus
from events.event_list import RAG_RETRIEVED
from rag.index import Hit
from rag.knowledge import Knowledge
from config.settings import settings
import argparse
import json
import os
import re
import statistics
import sys

# Where the launcher of install.sh keeps the index (LOUIS_RAG): the one louis uses outside the repository
GLOBAL_INDEX: str = os.path.expanduser("~/.local/share/louis/louis.rag.db")
# Passages looked at to find the rank of an answer missed in the k
DEPTH: int = 20
# A question still to write: left out of the run
PLACEHOLDER: str = "TODO"
# The thresholds of the reranker tried in the table: its scores go from 0 to 1
THRESHOLDS: tuple[float, ...] = (0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5)
EXPECTED: re.Pattern = re.compile(r"^(?P<path>.+?)(?::(?P<start>\d+)-(?P<end>\d+))?$")

@dataclass(frozen=True, slots=True)
class Expected:
    """ A passage that answers: a path from the root of the source, and its lines (None: anywhere in the file) """
    path : str
    start: int | None
    end  : int | None

@dataclass(slots=True)
class Result:
    """ How the search did on one question """
    question    : str
    kind        : str
    answerable  : bool
    rank        : int | None     # of the first right passage in the k search_knowledge returns, None if not there
    deep_rank   : int | None     # the same in the DEPTH first ones, nothing dropped by the threshold
    answer_score: float | None   # the score of the first right passage in the DEPTH first ones
    top_score   : float | None   # the score of the first passage found, whatever it is, nothing dropped
    returned    : int            # passages in the k (fewer than k once a threshold drops some)
    hits        : list[str]      # the k passages, as "path:start-end (score)"
    filters     : dict | None = None   # the filters on the files searched with, None without

def parse_expected(text: str) -> Expected:
    """ "/src/app.py:120-180" or "/src/app.py", as search_knowledge writes them """
    match = EXPECTED.match(text.strip())
    path: str = "/" + match["path"].lstrip("/")
    return Expected(path, int(match["start"]), int(match["end"])) if match["start"] else Expected(path, None, None)

def matches(hit: Hit, expected: Expected) -> bool:
    """ Whether a passage found is (or overlaps) one that answers """
    if hit.path != expected.path:
        return False
    return expected.start is None or (hit.start <= expected.end and expected.start <= hit.end)

def rank_of(hits: list[Hit], expected: list[Expected]) -> int | None:
    """ The rank (from 1) of the first passage that answers, None if none does """
    return next((i for i, hit in enumerate(hits, 1) if any(matches(hit, e) for e in expected)), None)

def load_questions(path: str) -> tuple[str | None, list[dict]]:
    """ The source and the questions of the file, those still to write left out """
    with open(path, encoding="utf-8") as file:
        data: dict = json.load(file)
    questions: list[dict] = [q for q in data.get("questions", []) if not q.get("question", "").startswith(PLACEHOLDER)]
    skipped: int = len(data.get("questions", [])) - len(questions)
    if skipped:
        print(f"{skipped} question(s) encore à écrire ({PLACEHOLDER}...) : laissée(s) de côté.")
    source: str | None = data.get("source")
    return (None if not source or source.startswith(PLACEHOLDER) else source), questions

def evaluate(knowledge: Knowledge, source: str | None, question: dict, k: int, filtered: bool = True) -> Result:
    """ Search a question as search_knowledge does, then deeper: with its filters, when it has some and filtered is True """
    expected: list[Expected] = [parse_expected(e) for e in question.get("expected", [])]
    filters: dict = {key: value for key, value in (question.get("filters") or {}).items() if key in ("path", "kind") and value}
    if not filtered:
        filters = {}
    hits: list[Hit] = knowledge.search(question["question"], source, k, **filters).hits
    deep: list[Hit] = knowledge.search(question["question"], source, DEPTH, drop=False, **filters).hits
    deep_rank: int | None = rank_of(deep, expected) if expected else None
    return Result(
        question=question["question"],
        kind=question.get("kind") or ("hors sujet" if not expected else "?"),
        answerable=bool(expected),
        rank=rank_of(hits, expected) if expected else None,
        deep_rank=deep_rank,
        answer_score=deep[deep_rank - 1].score if deep_rank else None,
        top_score=deep[0].score if deep else None,
        returned=len(hits),
        hits=[f"{hit.path}:{hit.start}-{hit.end} ({hit.score})" for hit in hits],
        filters=filters or None
    )

def summarize(results: list[Result], k: int) -> dict:
    """ The metrics of the run: overall, by kind of question, and the scores of the answers next to the noise """
    def scores(values: list[float | None]) -> dict | None:
        values = [v for v in values if v is not None]
        if not values:
            return None
        return {"min": min(values), "median": round(statistics.median(values), 4), "max": max(values)}

    def recall(group: list[Result]) -> dict:
        return {
            "questions": len(group),
            "hit@1": round(sum(r.rank == 1 for r in group) / len(group), 3),
            f"hit@{k}": round(sum(r.rank is not None for r in group) / len(group), 3),
            f"hit@{DEPTH}": round(sum(r.deep_rank is not None for r in group) / len(group), 3),
            # The mean of 1 / rank: 1 when the answer always comes first, 0 when it is never found
            "mrr": round(sum(1 / r.deep_rank for r in group if r.deep_rank) / len(group), 3),
        }

    answerable: list[Result] = [r for r in results if r.answerable]
    noise: list[Result] = [r for r in results if not r.answerable]
    summary: dict = {"answerable": recall(answerable) if answerable else None, "by_kind": {}}
    for kind in sorted({r.kind for r in answerable}):
        summary["by_kind"][kind] = recall([r for r in answerable if r.kind == kind])
    summary["unanswerable"] = {
        "questions": len(noise),
        # Once a threshold drops the near-misses, this should go down to 0
        "returned_avg": round(sum(r.returned for r in noise) / len(noise), 2),
    } if noise else None
    summary["scores"] = {
        "right_answer": scores([r.answer_score for r in answerable]),
        "best_noise": scores([r.top_score for r in noise]),
    }
    return summary

def thresholds(results: list[Result], k: int) -> list[dict]:
    """
        What each threshold of the reranker would do: the right answers it keeps in the k (ranked first, and over it),
        and the questions with no answer that it would give nothing back to (all their passages under it)
    """
    answerable: list[Result] = [r for r in results if r.answerable]
    noise: list[Result] = [r for r in results if not r.answerable]
    rows: list[dict] = []
    for threshold in THRESHOLDS:
        kept: int = sum(1 for r in answerable if r.deep_rank and r.deep_rank <= k and r.answer_score >= threshold)
        silenced: int = sum(1 for r in noise if r.top_score is None or r.top_score < threshold)
        rows.append({
            "min_score": threshold,
            f"hit@{k}": round(kept / len(answerable), 3) if answerable else None,
            "noise_silenced": round(silenced / len(noise), 3) if noise else None,
        })
    return rows

def show(results: list[Result], summary: dict, k: int, baseline: dict[str, dict] | None,
         table: list[dict] | None = None) -> None:
    """ Each question, then the metrics """
    for r in results:
        if r.answerable:
            mark: str = "✓" if r.rank else "✗"
            where: str = f"rang {r.rank}" if r.rank else (f"rang {r.deep_rank} (hors des {k})" if r.deep_rank
                                                          else f"absent des {DEPTH}")
        else:
            mark, where = "·", f"{r.returned} passage(s) renvoyé(s)"
        change: str = ""
        if baseline and (before := baseline.get(r.question)) is not None and r.answerable:
            old, new = before.get("deep_rank") or DEPTH + 1, r.deep_rank or DEPTH + 1
            change = "  mieux" if new < old else "  pire" if new > old else ""
        tag: str = (" {" + ", ".join(f"{key}={value}" for key, value in r.filters.items()) + "}") if r.filters else ""
        print(f"{mark} [{r.kind}]{tag} {r.question}\n    {where}{change}")
        if r.answerable and r.rank != 1:
            for hit in r.hits:
                print(f"      {hit}")

    print()
    if summary["answerable"]:
        print(f"Questions avec réponse : {json.dumps(summary['answerable'], ensure_ascii=False)}")
        for kind, values in summary["by_kind"].items():
            print(f"  {kind:<14} {json.dumps(values, ensure_ascii=False)}")
    if summary["unanswerable"]:
        print(f"Questions hors sujet   : {json.dumps(summary['unanswerable'], ensure_ascii=False)}")
    right, noise = summary["scores"]["right_answer"], summary["scores"]["best_noise"]
    print(f"Scores bonne réponse   : {right}")
    print(f"Scores meilleur bruit  : {noise}")
    if right and noise:
        verdict: str = ("un seuil les sépare" if right["min"] > noise["max"]
                        else "ils se chevauchent : aucun seuil ne garde toutes les réponses et jette tout le bruit")
        print(f"  -> {verdict}")
    if table:
        print(f"\nSeuils (rag.rerank.min_score) : bonnes réponses gardées dans les {k}, questions hors sujet sans aucun passage")
        for row in table:
            print(f"  {row['min_score']:<5} hit@{k} {row[f'hit@{k}']:<6} bruit écarté {row['noise_silenced']}")

def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m rag.evaluate", description="Mesure la recherche de la base de connaissances")
    parser.add_argument("questions", help="le fichier des questions (voir docs/rag_eval.json)")
    parser.add_argument("--db", default=None, help=f"l'index (défaut : LOUIS_RAG, sinon {GLOBAL_INDEX} s'il existe, sinon celui du dossier courant)")
    parser.add_argument("--source", default=None, help="la source où chercher (défaut : celle du fichier, sinon toutes)")
    parser.add_argument("-k", type=int, default=settings.get("rag.results", 4), help="passages renvoyés, comme search_knowledge (défaut : rag.results)")
    parser.add_argument("--save", default=None, help="écrit les résultats dans ce fichier JSON")
    parser.add_argument("--baseline", default=None, help="un fichier écrit par --save, pour comparer les rangs question par question")
    parser.add_argument("--no-rerank", action="store_true", help="sans le reranker : l'ordre de l'index seul")
    parser.add_argument("--rerank-model", default=None, help="un autre modèle de reranking (défaut : rag.rerank.model)")
    parser.add_argument("--min-score", type=float, default=None, help="un autre seuil du reranker (défaut : rag.rerank.min_score)")
    parser.add_argument("--max-chars", type=int, default=None, help="ce que le reranker lit de chaque passage (défaut : rag.rerank.max_chars, 0 : tout)")
    parser.add_argument("--no-filters", action="store_true", help="sans les filtres (path, kind) des questions")
    args: argparse.Namespace = parser.parse_args()

    # Knowledge.from_settings reads the path of the index there, as louis does
    db: str | None = args.db or os.environ.get("LOUIS_RAG") or (GLOBAL_INDEX if os.path.exists(GLOBAL_INDEX) else None)
    if db:
        os.environ["LOUIS_RAG"] = db
    config: dict = dict(settings)
    if args.no_rerank:
        config["rag.rerank.enabled"] = False
    if args.rerank_model:
        config["rag.rerank.enabled"], config["rag.rerank.model"] = True, args.rerank_model
    if args.min_score is not None:
        config["rag.rerank.min_score"] = args.min_score
    if args.max_chars is not None:
        config["rag.rerank.max_chars"] = args.max_chars
    bus: EventBus = EventBus()
    events: list[dict] = []
    bus.subscribe(lambda event: events.append(event.data), RAG_RETRIEVED)
    knowledge: Knowledge = Knowledge.from_settings(config, bus)
    print(f"Index : {knowledge.path}")

    file_source, questions = load_questions(args.questions)
    source: str | None = args.source or file_source
    names: list[str] = [known["name"] for known in knowledge.sources()]
    if knowledge.empty:
        sys.stderr.write("L'index est vide : indexe d'abord ton projet (louis --index <dossier> --name <nom>).\n")
        return 1
    if source is not None and source not in names:
        sys.stderr.write(f"La source '{source}' n'est pas dans l'index. Les sources sont : {', '.join(names)}.\n")
        return 1
    if not questions:
        sys.stderr.write(f"Aucune question à poser : remplace les {PLACEHOLDER} de {args.questions}.\n")
        return 1
    wanted: str | None = config["rag.rerank.model"] if config.get("rag.rerank.enabled") else None
    print(f"Source : {source or 'toutes'}, k = {args.k}, {len(questions)} question(s), "
          f"reranker : {wanted or 'aucun'}" + (f" (seuil {config.get('rag.rerank.min_score', 0.0)})" if wanted else "") + "\n")

    results: list[Result] = [evaluate(knowledge, source, question, args.k, not args.no_filters) for question in questions]
    keyword: int = sum(1 for e in events if e["mode"] == "keyword")
    if keyword:
        print(f"Attention : {keyword} recherche(s) par mots-clés seulement (Ollama ou "
              f"{settings.get('rag.embed.model')} ne répond pas) : les chiffres ne valent pas la recherche hybride.\n")
    reranked: list[dict] = [e for e in events if e.get("reranker")]
    if wanted and len(reranked) < len(events):
        print(f"Attention : {len(events) - len(reranked)} recherche(s) sans reranking ({wanted} n'a pas pu servir, "
              "voir louis.log) : les chiffres mélangent les deux.\n")

    baseline: dict[str, dict] | None = None
    if args.baseline:
        with open(args.baseline, encoding="utf-8") as file:
            baseline = {r["question"]: r for r in json.load(file)["results"]}
    summary: dict = summarize(results, args.k)
    # The scores of the fusion are no relevance: a threshold on them means nothing
    table: list[dict] | None = thresholds(results, args.k) if reranked else None
    if reranked:
        # The first one loads the model: it is left out of the time of a search
        times: list[float] = sorted(e["rerank"] for e in reranked[1:]) or [reranked[0]["rerank"]]
        summary["rerank_seconds"] = {"median": times[len(times) // 2], "max": times[-1], "first": reranked[0]["rerank"]}
    show(results, summary, args.k, baseline, table)
    if reranked:
        print(f"\nTemps du reranking : {summary['rerank_seconds']} (first : avec le chargement du modèle)")

    if args.save:
        with open(args.save, "w", encoding="utf-8") as file:
            json.dump({
                "date": datetime.now().isoformat(timespec="seconds"), "index": knowledge.path, "source": source,
                "k": args.k, "embed_model": settings.get("rag.embed.model"),
                "reranker": wanted, "min_score": config.get("rag.rerank.min_score") if wanted else None,
                "summary": summary, "thresholds": table, "results": [asdict(r) for r in results]
            }, file, ensure_ascii=False, indent=2)
        print(f"\nRésultats écrits dans {args.save}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
