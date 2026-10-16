##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Evaluate the thresholds of the semantic cache: how close the questions that mean the same are, and the others
##
## Usage:  cd src && python -m cache.evaluate [--json out.json]
##
## Two kinds of pairs, a question stored and a new one, read as the cache reads them: by the embedding model of the
## settings (rag.embed.model, Ollama must run), then by the reranker (rag.rerank.model, fastembed):
##   same    the same question in other words: the cache should give the answer again (recall)
##   other   a question close in words but asking for something else: the cache must never give it (false hits)
## A pair is served when it is close enough in meaning (cache.threshold), about the same details (numbers, files, names
## of the code) and the same question for the reranker (cache.rerank.min_score). Each threshold is moved with the other
## one as it is set. Take the lowest ones with no false hit: a wrong answer given at once is worse than a right one
## given slowly
##
from cache.rules import same_specifics
from cache.store import normalized
from config.settings import settings
from rag.embedder import Embedder, EmbedError
from rag.reranker import Reranker, RerankError
import argparse
import json
import sys

SAME: list[tuple[str, str]] = [
    ("Comment lire un fichier JSON en Python ?", "Comment on lit un fichier JSON avec Python ?"),
    ("Qu'est-ce qu'une closure ?", "C'est quoi une closure ?"),
    ("Comment trier une liste de dictionnaires par une clé ?", "Comment trier une liste de dicts selon une clé ?"),
    ("Quelle est la différence entre une liste et un tuple ?", "Liste ou tuple : quelle différence ?"),
    ("Comment créer un environnement virtuel Python ?", "Comment je crée un venv en Python ?"),
    ("Comment annuler le dernier commit git ?", "Comment défaire mon dernier commit avec git ?"),
    ("À quoi sert le mot-clé yield ?", "Que fait yield en Python ?"),
    ("Comment inverser une chaîne de caractères en Python ?", "Comment renverser une string en Python ?"),
    ("Combien font 17 × 23 ?", "17 fois 23, ça fait combien ?"),
    ("Comment lire un fichier ligne par ligne ?", "Lire un fichier ligne à ligne, comment faire ?"),
    ("Qu'est-ce qu'un décorateur en Python ?", "Explique-moi les décorateurs Python"),
    ("How do I read a JSON file in Python?", "How to read JSON from a file with Python?"),
]

OTHER: list[tuple[str, str]] = [
    ("Comment lire un fichier JSON en Python ?", "Comment écrire un fichier JSON en Python ?"),
    ("Comment lire un fichier JSON en Python ?", "Comment lire un fichier CSV en Python ?"),
    ("Comment trier une liste par ordre croissant ?", "Comment trier une liste par ordre décroissant ?"),
    ("Quelle est la différence entre une liste et un tuple ?", "Quelle est la différence entre une liste et un set ?"),
    ("Comment annuler le dernier commit git ?", "Comment modifier le message du dernier commit git ?"),
    ("Combien font 17 × 23 ?", "Combien font 17 × 24 ?"),
    ("Comment créer une branche git ?", "Comment supprimer une branche git ?"),
    ("Comment ajouter un élément à une liste ?", "Comment retirer un élément d'une liste ?"),
    ("Que fait config.py ?", "Que fait settings.py ?"),
    ("Comment convertir une chaîne en entier ?", "Comment convertir un entier en chaîne ?"),
    ("Qu'est-ce qu'une closure en Python ?", "Qu'est-ce qu'une closure en JavaScript ?"),
    ("How do I read a JSON file in Python?", "How do I write a JSON file in Python?"),
]

THRESHOLDS: list[float] = [round(0.70 + 0.02 * i, 2) for i in range(14)]
MIN_SCORES: list[float] = [round(0.05 * i, 2) for i in range(13)]

def scores(embedder: Embedder, reranker: Reranker, pairs: list[tuple[str, str]]) -> list[dict]:
    """ The cosine of each pair, the score of the reranker, and whether its details are the same. NOTE: Raisable """
    found: list[dict] = []
    for stored, asked in pairs:
        a, b = normalized(embedder.query(stored)), normalized(embedder.query(asked))
        found.append({"stored": stored, "asked": asked, "score": round(float(a @ b), 4),
                      "verified": round(reranker.score(asked, [stored])[0], 4),
                      "specifics": same_specifics(stored, asked)})
    return found

def served(pairs: list[dict], threshold: float, min_score: float) -> int:
    """ The pairs the cache would answer with these thresholds """
    return sum(1 for pair in pairs if pair["score"] >= threshold and pair["specifics"] and pair["verified"] >= min_score)

def table(same: list[dict], other: list[dict], name: str, values: list[float], served_at) -> None:
    """ The recall and the false hits for each value of one threshold """
    print(f"{name:<18} recall   false hits")
    for value in values:
        hits, false = served_at(value)
        print(f"  {value:<14.2f}  {hits / len(same):>5.0%}   {false:>3} / {len(other)}")
    print()

def main() -> int:
    parser = argparse.ArgumentParser(description="Mesure les seuils du cache sémantique")
    parser.add_argument("--json", help="écrit les scores dans ce fichier")
    options = parser.parse_args()
    embedder = Embedder(settings["chat.uri"], settings["rag.embed.model"], settings.get("rag.embed.query_prefix", ""),
                        settings.get("rag.embed.document_prefix", ""), gpu=False)
    reranker = Reranker(settings["rag.rerank.model"])
    try:
        same, other = scores(embedder, reranker, SAME), scores(embedder, reranker, OTHER)
    except (EmbedError, RerankError) as e:
        print(f"Erreur : {e.message}", file=sys.stderr)
        return 1
    threshold: float = settings["cache.threshold"]
    min_score: float = settings["cache.rerank.min_score"]

    print(f"{embedder.model} + {reranker.model} · {len(same)} paraphrases, {len(other)} near-misses\n")
    table(same, other, f"threshold (rerank ≥ {min_score})", THRESHOLDS,
          lambda value: (served(same, value, min_score), served(other, value, min_score)))
    table(same, other, f"rerank (threshold ≥ {threshold})", MIN_SCORES,
          lambda value: (served(same, threshold, value), served(other, threshold, value)))
    table(same, other, "meaning only", THRESHOLDS, lambda value: (served(same, value, 0.0), served(other, value, 0.0)))

    print("Each pair (cosine, reranker, ✓ same details):")
    for label, pairs in (("same", same), ("other", other)):
        for pair in sorted(pairs, key=lambda pair: -pair["score"]):
            mark: str = "✓" if pair["specifics"] else "✗"
            print(f"  {label:<5} {pair['score']:.3f}  {pair['verified']:.3f}  {mark}  {pair['stored']}  |  {pair['asked']}")
    hits, false = served(same, threshold, min_score), served(other, threshold, min_score)
    print(f"\nWith the settings (threshold {threshold}, rerank {min_score}): recall {hits / len(same):.0%}, "
          f"false hits {false} / {len(other)}")
    if options.json:
        with open(options.json, "w", encoding="utf-8") as file:
            json.dump({"embedder": embedder.model, "reranker": reranker.model, "same": same, "other": other}, file,
                      ensure_ascii=False, indent=2)
    return 0

if __name__ == "__main__":
    sys.exit(main())
