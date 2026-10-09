##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Metrics of a benchmark: what the judgments of its answers add up to, overall and by kind of question
##
from monitor.metrics import mean, ratio

# The metrics compared between two runs, and how many digits they keep
COMPARED: tuple[str, ...] = ("answered", "faithfulness", "relevance", "coherence", "flagged_rate", "contradicted")

def scores(judgments: list[dict | None]) -> dict:
    """
        The metrics of some answers: a None one got no answer (its turn failed) or no judgment. faithfulness is the
        mean over the answers that read a source, flagged_rate the share of all their claims not supported
    """
    done: list[dict] = [j for j in judgments if j is not None and j["status"] == "ok"]
    claims: list[dict] = [claim for j in done for claim in j["claims"]]
    contradicted: int = sum(1 for claim in claims if claim["verdict"] == "contradicted")
    faithful: list[float] = [j["faithfulness"] for j in done if j["faithfulness"] is not None]
    def rounded(value: float | None) -> float | None:
        return round(value, 3) if value is not None else None
    return {
        "questions"   : len(judgments),
        "answered"    : rounded(ratio(len(done), len(judgments))),
        "faithfulness": rounded(mean(faithful)),
        "sourced"     : len(faithful),
        "relevance"   : rounded(mean([j["relevance"] for j in done])),
        "coherence"   : rounded(mean([j["coherence"] for j in done])),
        "claims"      : len(claims),
        "flagged_rate": rounded(ratio(sum(1 for claim in claims if claim["verdict"] != "supported"), len(claims))),
        "contradicted": contradicted,
    }

def summary_of(results: list[tuple[str, dict | None]]) -> dict:
    """ The metrics of a run, from (kind, judgment) of each question: all of them, then by kind """
    kinds: dict[str, list[dict | None]] = {}
    for kind, judgment in results:
        kinds.setdefault(kind, []).append(judgment)
    return {
        "all": scores([judgment for _, judgment in results]),
        "by_kind": {kind: scores(judgments) for kind, judgments in sorted(kinds.items())},
    }

def deltas(before: dict, after: dict) -> dict[str, float]:
    """ What changed between the metrics of two runs, for those both have """
    return {name: round(after[name] - before[name], 3) for name in COMPARED
            if before.get(name) is not None and after.get(name) is not None}
