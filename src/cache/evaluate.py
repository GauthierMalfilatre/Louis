##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Evaluate the thresholds of the semantic cache: how close the questions that mean the same are, and the others
##
## Usage:  cd src && python -m cache.evaluate [--json out.json]
##
## Two kinds of pairs, a question stored and a new one, read as the cache reads them: by the embedding model of the
## settings (rag.embed.model, Ollama must run), the reranker (rag.rerank.model, fastembed) and the small model
## (cache.match.model, Ollama):
##   same    the same question in other words: the cache should give the answer again (recall)
##   other   a question close in words but asking for something else: the cache must never give it (false hits)
## A pair is served when the new question stands alone (cache/rules.py), is close enough in meaning (cache.threshold),
## about the same details (numbers, files, names of the code), and the same question for the reranker
## (cache.rerank.min_score) or else for the small model. Take the lowest threshold with no false hit: a wrong answer
## given at once is worse than a right one given slowly. Each question of the others that reaches the small model costs
## ~2.4 s to a miss: the lower the threshold, the more of them.
## The seed is measured apart: a question asked, and the question of the seed it should get (or must not get), the
## reranker reading the answer of the seed as the cache does (cache.seed.min_score)
##
from cache.matcher import Matcher, MatchError
from cache.rules import same_specifics, why_not
from cache.seeding import load as load_seed
from cache.store import normalized
from config.settings import settings
from rag.embedder import Embedder, EmbedError
from rag.reranker import Reranker, RerankError
import argparse
import json
import sys
import time

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
    ("Qu'est-ce que tu sais faire ?", "Qu'est ce que tu peux faire ?"),
    ("Qu'est-ce que tu sais faire ?", "Tu sais faire quoi ?"),
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
    ("Qu'est-ce que tu sais faire ?", "Qu'est-ce que tu ne sais pas faire ?"),
]

# (asked, the question of cache/seed/ it is about)
SEED_SAME: list[tuple[str, str]] = [
    ("Comment ajouter mes docs à la base de connaissances ?", "Comment ajouter de la documentation à la base de connaissances ?"),
    ("Quelles commandes je peux utiliser ?", "Quelles sont les commandes disponibles ?"),
    ("Comment exporter ma session en PDF ?", "Comment exporter une session en PDF ?"),
    ("Comment lancer Louis dans le navigateur ?", "Comment utiliser Louis dans le navigateur ?"),
    ("Comment reprendre une session ?", "Comment reprendre une ancienne session ?"),
    ("Comment je peux indexer mes fichiers de documentation ?", "Comment indexer un dossier ?"),
    ("Comment créer un lien de partage ?", "Comment créer un lien public vers une conversation ?"),
    ("Comment faire pour que tu réfléchisses avant de répondre ?", "Comment faire réfléchir le modèle avant de répondre ?"),
    ("Quels langages tu sais exécuter ?", "Quels langages peux-tu exécuter ?"),
    ("Comment couper le cache ?", "Comment désactiver le cache ?"),
]
# (asked, the question of the seed close to it, that it must not get): questions of code with the words of the seed
SEED_OTHER: list[tuple[str, str]] = [
    ("Comment indexer une liste en Python ?", "Comment indexer un dossier ?"),
    ("Comment installer numpy ?", "Comment installer Louis ?"),
    ("Comment exporter un DataFrame en CSV ?", "Comment exporter une session en PDF ?"),
    ("Comment lancer un serveur web en Python ?", "Comment lancer l'interface web ?"),
    ("Comment partager un dossier sur le réseau ?", "Comment partager une session ?"),
    ("Comment vider le cache de pip ?", "Comment vider le cache sémantique ?"),
    ("Comment exécuter un script bash ?", "Comment exécuter du code avec Louis ?"),
    ("Comment générer un PDF en Python ?", "Comment exporter une session en PDF ?"),
    ("Comment valider un JSON avec un schéma en Python ?", "Comment utiliser un schéma JSON avec Louis ?"),
    ("Comment désinstaller un paquet pip ?", "Comment désinstaller Louis ?"),
]

THRESHOLDS: list[float] = [round(0.66 + 0.02 * i, 2) for i in range(16)]

def read(embedder: Embedder, reranker: Reranker, matcher: Matcher | None, pairs: list[tuple[str, str]],
         seed: dict[str, str] | None = None) -> list[dict]:
    """
        Each pair (stored, asked) as the cache reads it: the cosine, the reranker (on the stored question, or the answer
        of the seed), the small model, the details, why the new question is not looked up. NOTE: Raisable
    """
    found: list[dict] = []
    for stored, asked in pairs:
        a, b = normalized(embedder.query(stored)), normalized(embedder.query(asked))
        start: float = time.perf_counter()
        matched: bool | None = matcher.same(stored, asked) if matcher is not None else None
        found.append({"stored": stored, "asked": asked, "score": round(float(a @ b), 4),
                      "verified": round(reranker.score(asked, [seed[stored] if seed else stored])[0], 4),
                      "matched": matched, "match_seconds": round(time.perf_counter() - start, 2),
                      "specifics": same_specifics(stored, asked), "why_not": why_not(asked)})
    return found

def served(pair: dict, threshold: float, min_score: float, matcher: bool = True) -> bool:
    """ Whether the cache gives the answer of the pair with these thresholds """
    return (pair["why_not"] is None and pair["score"] >= threshold and pair["specifics"]
            and (pair["verified"] >= min_score or (matcher and bool(pair["matched"]))))

def reaches(pair: dict, threshold: float, min_score: float) -> bool:
    """ Whether the pair is asked to the small model: close enough, not confirmed by the reranker """
    return (pair["why_not"] is None and pair["score"] >= threshold and pair["specifics"]
            and pair["verified"] < min_score)

def table(same: list[dict], other: list[dict], title: str, min_score: float) -> None:
    """ The recall, the false hits and the cost to the misses for each threshold, with the small model and without """
    print(f"{title}\n  threshold   reranker alone        + small model         asked to it (misses)")
    for threshold in THRESHOLDS:
        alone = (sum(served(p, threshold, min_score, False) for p in same), sum(served(p, threshold, min_score, False) for p in other))
        both = (sum(served(p, threshold, min_score) for p in same), sum(served(p, threshold, min_score) for p in other))
        cost: int = sum(reaches(p, threshold, min_score) for p in other)
        print(f"  {threshold:.2f}        {alone[0]:>2}/{len(same)} · {alone[1]} false     "
              f"{both[0]:>2}/{len(same)} · {both[1]} false     {cost:>2}/{len(other)}")
    print()

def main() -> int:
    parser = argparse.ArgumentParser(description="Mesure les seuils du cache sémantique")
    parser.add_argument("--json", help="écrit les scores dans ce fichier")
    options = parser.parse_args()
    embedder = Embedder(settings["chat.uri"], settings["rag.embed.model"], settings.get("rag.embed.query_prefix", ""),
                        settings.get("rag.embed.document_prefix", ""), gpu=False)
    reranker = Reranker(settings["rag.rerank.model"], max_chars=settings.get("rag.rerank.max_chars", 0))
    model: str | None = settings.get("cache.match.model")
    matcher: Matcher | None = Matcher(settings["chat.uri"], model, settings.get("cache.match.gpu", False)) if model else None
    answers: dict[str, str] = dict(load_seed()[1])
    try:
        if matcher is not None:
            matcher.same("Louis", "Louis")
        same, other = read(embedder, reranker, matcher, SAME), read(embedder, reranker, matcher, OTHER)
        seed_same = read(embedder, reranker, matcher, [(s, a) for a, s in SEED_SAME], answers)
        seed_other = read(embedder, reranker, matcher, [(s, a) for a, s in SEED_OTHER], answers)
    except (EmbedError, RerankError, MatchError) as e:
        print(f"Erreur : {e.message}", file=sys.stderr)
        return 1
    threshold: float = settings["cache.threshold"]
    min_score: float = settings["cache.rerank.min_score"]
    seed_min: float = settings["cache.seed.min_score"]

    print(f"{embedder.model} + {reranker.model} + {model or 'no small model'}\n")
    table(same, other, f"Answers of the model ({len(same)} paraphrases, {len(other)} near-misses, rerank ≥ {min_score})",
          min_score)
    table(seed_same, seed_other, f"The seed ({len(seed_same)} questions about Louis, {len(seed_other)} questions of code "
          f"that look like them, rerank ≥ {seed_min} on the answer)", seed_min)

    print("Each pair (cosine, reranker, small model, ✓ same details, why it is not looked up):")
    for label, pairs in (("same", same + seed_same), ("other", other + seed_other)):
        for pair in sorted(pairs, key=lambda pair: -pair["score"]):
            judged: str = "–" if pair["matched"] is None else "same" if pair["matched"] else "diff"
            print(f"  {label:<5} {pair['score']:.3f}  {pair['verified']:.3f}  {judged:<4}  "
                  f"{'✓' if pair['specifics'] else '✗'}  {pair['why_not'] or '':<8}  {pair['stored']}  |  {pair['asked']}")
    seconds: list[float] = sorted(pair["match_seconds"] for pair in same + other + seed_same + seed_other)
    if matcher is not None:
        print(f"\nSmall model: median {seconds[len(seconds) // 2]:.2f}s, max {seconds[-1]:.2f}s a question")
    for title, s, o, minimum in (("Model", same, other, min_score), ("Seed", seed_same, seed_other, seed_min)):
        print(f"{title}, with the settings (threshold {threshold}): recall "
              f"{sum(served(p, threshold, minimum) for p in s)}/{len(s)}, false hits "
              f"{sum(served(p, threshold, minimum) for p in o)}/{len(o)}")
    if options.json:
        with open(options.json, "w", encoding="utf-8") as file:
            json.dump({"embedder": embedder.model, "reranker": reranker.model, "matcher": model, "same": same,
                       "other": other, "seed_same": seed_same, "seed_other": seed_other}, file, ensure_ascii=False,
                      indent=2)
    return 0

if __name__ == "__main__":
    sys.exit(main())
