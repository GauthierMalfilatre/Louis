##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Benchmark: Louis answers a fixed set of questions, the judge scores each answer, and the run is compared with another:
##   cd src && python -m eval.bench ../docs/eval_questions.json [--save after.json] [--baseline before.json]
##
## The whole of Louis answers, as for the user: its prompt, its tools, its guard, its knowledge base. Only the user is
## scripted: a new session for each question (/clear), and nobody to grant a permission (a tool never writes).
## Compare two versions on the same questions: --save with one, --baseline with the other. A version is a prompt
## (--prompt), a model (--model), or the code of a branch. The answers and their sources are saved whole: RAGAS reads
## them as they are (the "ragas" of each result), and the pairwise comparison of two runs will too
##
from dataclasses import dataclass, field
from datetime import datetime
from app.app import App
from config.prompt import SYSTEM_PROMPT
from config.settings import settings
from eval.judge import Judgment
from eval.metrics import summary_of, deltas
from eval.sample import Sample
from events.event import Event
from events.event_bus import EventBus
from events.event_list import CHAT_TURN_ENDED, EVAL_SCORED
from interface.quiet import QuietInterface
from model.model_exception import ModelException
from monitor.recorder import Recorder, prompt_version
from session.user import User
import argparse
import json
import os
import sys

# A question still to write: left out of the run
PLACEHOLDER: str = "TODO"

@dataclass
class Result:
    """ How Louis did on one question: how its turn ended, and what the judge said of its answer """
    question : str
    kind     : str
    reference: str | None
    reason   : str | None  = None
    message  : str | None  = None
    judgment : dict | None = None
    ragas    : dict | None = None
    sources  : list[str]   = field(default_factory=list)

class ScriptedUser(QuietInterface):
    """ The user of the benchmark: each question in a new session, what happened to it kept with it """
    def __init__(self, results: list[Result]):
        super().__init__()
        self.__results: list[Result] = results
        self.__lines  : list[tuple[str, int | None]] = [line for i, r in enumerate(results)
                                                        for line in (("/clear", None), (r.question, i))]
        self.__current: Result | None = None

    def bind(self, bus: EventBus) -> "ScriptedUser":
        """ The errors on stderr, as --ask does, and how each turn ended """
        super().bind(bus)
        bus.subscribe(self.__on_turn_ended, CHAT_TURN_ENDED)
        return self

    def getUserInput(self) -> str:
        """ The next line of the script: EOFError at its end """
        if not self.__lines:
            raise EOFError
        line, index = self.__lines.pop(0)
        if index is not None:
            self.__current = self.__results[index]
            print(f"[{index + 1}/{len(self.__results)}] {line}", file=sys.stderr, flush=True)
        return line

    def on_judged(self, judgment: dict, sample: Sample | None) -> None:
        """
            The judgment of the answer to the current question (judged before its turn is told to have ended), and the
            sample as RAGAS reads it, with the reference answer of the question
        """
        if self.__current is None:
            return
        self.__current.judgment = judgment
        if sample is not None:
            sample.reference = self.__current.reference
            self.__current.ragas = sample.to_ragas()

    def __on_turn_ended(self, event: Event) -> None:
        if self.__current is not None:
            self.__current.reason, self.__current.message = event.data["reason"], event.data.get("message")

def load_questions(path: str) -> list[Result]:
    """ The questions of the file, those still to write left out """
    with open(path, encoding="utf-8") as file:
        data: dict = json.load(file)
    questions: list[dict] = [q for q in data.get("questions", []) if not q.get("question", "").startswith(PLACEHOLDER)]
    skipped: int = len(data.get("questions", [])) - len(questions)
    if skipped:
        print(f"{skipped} question(s) encore à écrire ({PLACEHOLDER}...) : laissée(s) de côté.")
    return [Result(q["question"], q.get("kind") or "?", q.get("reference")) for q in questions]

def score(value, scale: str) -> str:
    """ A score as shown: 83 %, 4/5, or – without one """
    if value is None:
        return "–"
    return f"{round(value * 100)} %" if scale == "%" else f"{value:g}/5"

def show(results: list[Result], summary: dict, baseline: dict | None) -> None:
    """ Each question, then the metrics, and what changed since the baseline """
    before: dict[str, dict] = {r["question"]: r for r in (baseline or {}).get("results", [])}
    for r in results:
        j: dict | None = r.judgment
        if r.reason != "done" or j is None or j["status"] != "ok":
            why: str = j["error"] if j and j["status"] != "ok" else (r.message or r.reason or "pas de réponse")
            print(f"✗ [{r.kind}] {r.question}\n    non évaluée : {why}")
            continue
        flagged: list[dict] = [c for c in j["claims"] if c["verdict"] != "supported"]
        change: str = ""
        if (old := (before.get(r.question) or {}).get("judgment")) and old.get("status") == "ok":
            moves: list[str] = [f"{name} {old[name]}→{j[name]}" for name in ("relevance", "coherence")
                                if old.get(name) is not None and j[name] is not None and old[name] != j[name]]
            if old.get("faithfulness") != j["faithfulness"]:
                moves.insert(0, f"fidélité {score(old.get('faithfulness'), '%')}→{score(j['faithfulness'], '%')}")
            change = ("  (" + ", ".join(moves) + ")") if moves else ""
        print(f"{'!' if flagged else '✓'} [{r.kind}] {r.question}\n"
              f"    fidélité {score(j['faithfulness'], '%')} · pertinence {score(j['relevance'], '/5')} · "
              f"cohérence {score(j['coherence'], '/5')} · {len(r.sources)} source(s){change}")
        for claim in flagged:
            print(f"      {'✗' if claim['verdict'] == 'contradicted' else '?'} {claim['text']}")

    print()
    for name, values in [("Toutes", summary["all"]), *summary["by_kind"].items()]:
        print(f"{name:<14} {json.dumps(values, ensure_ascii=False)}")
    if baseline:
        print(f"\nDepuis {baseline.get('date')} ({baseline.get('model')}, prompt {baseline.get('prompt')}) :")
        for name, delta in deltas(baseline["summary"]["all"], summary["all"]).items():
            print(f"  {name:<14} {delta:+g}")

def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.bench", description="Fait répondre Louis à des questions, et note ses réponses")
    parser.add_argument("questions", help="le fichier des questions (voir docs/eval_questions.json)")
    parser.add_argument("--save", default=None, help="écrit les résultats (réponses, sources, notes) dans ce fichier JSON")
    parser.add_argument("--baseline", default=None, help="un fichier écrit par --save, pour comparer question par question")
    parser.add_argument("--prompt", default=None, help="un fichier de prompt système à la place de celui de Louis")
    parser.add_argument("--model", default=None, help="le modèle qui répond, nom:taille (défaut : chat.model.*)")
    parser.add_argument("--judge", default=None, help="le modèle qui juge (défaut : eval.model, sinon celui qui répond)")
    parser.add_argument("--traces", default=None, help="enregistre aussi les appels dans ce fichier de traces (louis --dashboard)")
    args: argparse.Namespace = parser.parse_args()

    results: list[Result] = load_questions(args.questions)
    if not results:
        sys.stderr.write(f"Aucune question à poser : remplace les {PLACEHOLDER} de {args.questions}.\n")
        return 1
    config: dict = {**settings, "eval.enabled": True, "eval.background": False, "eval.sample": 1.0}
    if args.model:
        name, _, size = args.model.partition(":")
        config["chat.model.name"], config["chat.model.parameters"] = name, size or "latest"
    if args.judge:
        config["eval.model"] = args.judge
    prompt: str = SYSTEM_PROMPT
    if args.prompt:
        with open(args.prompt, encoding="utf-8") as file:
            prompt = file.read()

    user: ScriptedUser = ScriptedUser(results)
    try:
        app: App = App(config, prompt, User.anonymous(), user, Recorder(args.traces, config) if args.traces else None)
    except ModelException as e:
        sys.stderr.write(f"Le modèle ne répond pas : {e.message}\n")
        return 1
    # Judged at once (no background): the last judgment of the evaluator is this one, with its sources whole
    def judged(event: Event) -> None:
        judgment: Judgment | None = app.evaluator.last()
        user.on_judged(event.data, judgment.sample if judgment is not None else None)
    app.events.subscribe(judged, EVAL_SCORED)
    print(f"Modèle : {app.model.model}, juge : {app.evaluator.judge.model}, prompt {prompt_version(prompt.rstrip())}, "
          f"{len(results)} question(s)\n", file=sys.stderr)
    app.run()

    for r in results:
        if r.judgment is not None:
            r.sources = [f"{s['tool']} {json.dumps(s['arguments'], ensure_ascii=False)}" for s in r.judgment["sources"]]
    summary: dict = summary_of([(r.kind, r.judgment if r.reason == "done" else None) for r in results])
    baseline: dict | None = None
    if args.baseline:
        with open(args.baseline, encoding="utf-8") as file:
            baseline = json.load(file)
    show(results, summary, baseline)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as file:
            json.dump({
                "date": datetime.now().isoformat(timespec="seconds"), "model": app.model.model,
                "prompt": prompt_version(prompt.rstrip()), "judge": app.evaluator.judge.model,
                "questions": os.path.abspath(args.questions),
                "settings": {key: config.get(key) for key in ("chat.options", "guard.enabled", "rag.enabled",
                                                                "rag.rerank.enabled", "eval.sources")},
                "summary": summary, "results": [r.__dict__ for r in results]
            }, file, ensure_ascii=False, indent=2, default=str)
        print(f"\nRésultats écrits dans {args.save}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
