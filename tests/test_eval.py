##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of eval/: the samples made from the bus, the judge (its model scripted), the evaluator and the metrics
##
import json
import os
import sys
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from eval.collector import Collector
from eval.focus import focus, windows, terms, names, anchors, NOTHING
from eval.evaluator import Evaluator
from eval.judge import Judge, JudgeError, CLAIMS_SCHEMA, VERIFY_SCHEMA, RUBRIC_SCHEMA, fit, sources_text, NO_SOURCE
from eval.judge import normalized, merged
from eval.metrics import summary_of, deltas
from eval.sample import Sample, Source
from events.event_bus import EventBus
from events.event_list import *
from monitor.metrics import eval_stats
from monitor.recorder import Recorder

SOURCE: str = "def load(path):\n    return json.load(open(path))\n"

class ScriptedJudge(Judge):
    """ A judge whose model answers what the test says, by step; and that counts the requests """
    def __init__(self, claims=None, verdicts=None, rubric=None, fail=False, again=None, recheck=0):
        """ again: the verdicts of the second looks, one list per request (the flagged claims, in order) """
        super().__init__("http://localhost:0", "juge", 4096, recheck=recheck)
        self.replies = {
            id(CLAIMS_SCHEMA): {"claims": claims or []},
            id(VERIFY_SCHEMA): {"verdicts": verdicts or []},
            id(RUBRIC_SCHEMA): rubric or {"relevance": {"reason": "r", "score": 4}, "coherence": {"reason": "c", "score": 5}},
        }
        self.again: list[list[dict]] = list(again or [])
        self.asked: list[str] = []
        self.prompts: list[str] = []
        self.fail: bool = fail

    def ask(self, instructions, prompt, schema, examples=()):
        step: str = {id(CLAIMS_SCHEMA): "claims", id(VERIFY_SCHEMA): "verify", id(RUBRIC_SCHEMA): "rubric"}[id(schema)]
        if step == "verify" and "verify" in self.asked:
            step = "again"
        self.asked.append(step)
        self.prompts.append(prompt)
        if self.fail:
            raise JudgeError("Ollama ne répond pas")
        if step == "again":
            return {"verdicts": self.again.pop(0)}
        return self.replies[id(schema)]

def sample(sources=True) -> Sample:
    return Sample("s1", "Que fait load ?", "load lit un fichier JSON. Elle le met en cache.",
                  [Source("cat_file", {"path": "io.py"}, SOURCE)] if sources else [], "qwen", "abcd1234", 3)

def turn(bus, *, reply="La réponse.", reason="done", tools=(("cat_file", True),), refused=False):
    """ A turn of the app, as it goes on the bus """
    bus.dispatch(CHAT_TURN_STARTED)
    bus.dispatch(MODEL_CALL, model="qwen", system="Tu es Louis.", messages=[{"role": "system", "content": "x"},
                 {"role": "user", "content": "La question ?"}], tools=[], think=False, status="ok", error=None,
                 latency=1.0, reply=None)
    for name, ok in tools:
        bus.dispatch(TOOL_CALL_STARTED, name=name, arguments={"path": "a.py"}, producer="model")
        bus.dispatch(TOOL_CALL_ENDED, name=name, producer="model", ok=ok, result=f"résultat de {name}", duration=0.1)
    bus.dispatch(CHAT_REPLY, content="Je lis le fichier.", tools=["cat_file"])
    if refused:
        bus.dispatch(GUARD_TRIGGERED, stage="output", action="refused", rails=["self check output"], content="Non.")
    bus.dispatch(CHAT_REPLY, content=reply, tools=[])
    bus.dispatch(CHAT_TURN_ENDED, reason=reason, message=None)

class CollectorTest(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.samples: list[Sample] = []
        Collector(self.samples.append, ["cat_file", "search"]).bind(self.bus)

    def test_a_turn_done_gives_its_question_answer_and_sources(self):
        turn(self.bus, tools=(("cat_file", True), ("tree", True), ("search", False)))
        [s] = self.samples
        self.assertEqual((s.question, s.answer, s.model), ("La question ?", "La réponse.", "qwen"))
        # tree is no source, and a search that failed read nothing
        self.assertEqual([(source.tool, source.text) for source in s.sources], [("cat_file", "résultat de cat_file")])
        self.assertEqual(s.sources[0].arguments, {"path": "a.py"})
        self.assertEqual(s.to_ragas()["retrieved_contexts"], ["résultat de cat_file"])

    def test_no_sample_without_an_answer_to_judge(self):
        turn(self.bus, reason="cancelled")
        turn(self.bus, refused=True)
        turn(self.bus, reply="  ")
        self.assertEqual(self.samples, [])

    def test_the_session_of_the_answer(self):
        self.bus.dispatch(SESSION_SAVED, id=7)
        turn(self.bus)
        self.assertEqual(self.samples[0].session, 7)

class JudgeTest(unittest.TestCase):
    def test_fit_keeps_the_short_texts_whole(self):
        self.assertEqual(fit([10, 1000, 50], 300), [10, 240, 50])
        self.assertEqual(fit([10, 20], 1000), [10, 20])
        self.assertEqual(sum(fit([500, 500, 500], 900)), 900)

    def test_sources_are_numbered_and_cut(self):
        text = sources_text(Sample("s", "q", "a", [Source("cat_file", {"path": "a.py"}, "x" * 100),
                                                   Source("search", {"pattern": "y"}, "court")]), 60)
        self.assertIn('[1] cat_file {"path": "a.py"}', text)
        self.assertIn("[2] search", text)
        self.assertIn("coupé", text)
        self.assertIn("court", text)

    def test_claims_checked_against_the_sources(self):
        judge = ScriptedJudge(
            claims=["load lit un fichier JSON.", "load met le fichier en cache.", "load renvoie une liste.", "inventée"],
            verdicts=[
                {"claim": 1, "verdict": "supported", "source": 1, "evidence": "return json.load(open(path))"},
                {"claim": 2, "verdict": "unverifiable", "source": 0, "evidence": ""},
                # Supported, but by no source: a guess
                {"claim": 3, "verdict": "supported", "source": 9, "evidence": "x"},
                {"claim": 12, "verdict": "supported", "source": 1, "evidence": ""},
            ])
        judgment = judge.judge(sample())
        self.assertEqual(judge.asked, ["claims", "verify", "rubric"])
        self.assertEqual([c.verdict for c in judgment.claims], ["supported", "unverifiable", "unverifiable", "unverifiable"])
        self.assertTrue(judgment.claims[0].quoted)
        self.assertEqual(judgment.claims[3].reason, "le juge ne l'a pas vérifiée")
        self.assertEqual(judgment.faithfulness, 0.25)
        self.assertEqual((judgment.relevance, judgment.coherence), (4, 5))
        self.assertEqual(len(judgment.flagged), 3)

    def test_a_contradiction_comes_first_and_a_made_up_quote_is_told(self):
        judge = ScriptedJudge(claims=["a", "b"], verdicts=[
            {"claim": 1, "verdict": "unverifiable", "source": 0, "evidence": ""},
            {"claim": 2, "verdict": "contradicted", "source": 1, "evidence": "return yaml.load(f)"}])
        judgment = judge.judge(sample())
        self.assertEqual([c.text for c in judgment.flagged], ["b", "a"])
        self.assertFalse(judgment.claims[1].quoted)

    def test_a_second_look_at_the_flagged_claims_only(self):
        verdicts = [{"claim": 1, "verdict": "supported", "source": 1, "evidence": "return json.load(open(path))"},
                    {"claim": 2, "verdict": "unverifiable", "source": 0, "evidence": ""},
                    {"claim": 3, "verdict": "unverifiable", "source": 0, "evidence": ""},
                    {"claim": 4, "verdict": "contradicted", "source": 1, "evidence": "def load(path):"}]
        judge = ScriptedJudge(claims=["lit du JSON", "ouvre le fichier", "met en cache", "prend un chemin"], verdicts=verdicts,
                              recheck=3, again=[
            # Found this time, with a real quote: it wins
            [{"claim": 1, "verdict": "supported", "source": 1, "evidence": "open(path)"}],
            # A quote the source does not hold: the first verdict stays
            [{"claim": 1, "verdict": "supported", "source": 1, "evidence": "lru_cache"}],
            # A contradiction not found again is no longer told
            [{"claim": 1, "verdict": "unverifiable", "source": 0, "evidence": ""}]])
        judgment = judge.judge(sample())
        self.assertEqual(judge.asked, ["claims", "verify", "again", "again", "again", "rubric"])
        self.assertEqual([c.verdict for c in judgment.claims], ["supported", "supported", "unverifiable", "unverifiable"])
        self.assertEqual(judgment.claims[1].evidence, "open(path)")
        # Each second look reads its claim alone
        self.assertIn("1. ouvre le fichier", judge.prompts[2])
        self.assertNotIn("lit du JSON", judge.prompts[2])

    def test_nothing_flagged_no_second_look(self):
        judge = ScriptedJudge(claims=["lit du JSON"], verdicts=[
            {"claim": 1, "verdict": "unverifiable", "source": 0, "evidence": ""}], recheck=3)
        judge.judge(sample())
        # One claim was already checked alone
        self.assertEqual(judge.asked, ["claims", "verify", "rubric"])

    def test_the_judge_is_told_where_an_exact_name_is(self):
        judge = ScriptedJudge(claims=["`load` lit un fichier avec json.load", "elle met en cache"])
        judge.judge(sample())
        self.assertIn("1. `load` lit un fichier avec json.load  (cité tel quel dans : load → source 1, json.load → source 1)",
                      judge.prompts[1])
        self.assertIn("2. elle met en cache\n", judge.prompts[1] + "\n")

    def test_the_items_of_a_list_are_one_claim(self):
        self.assertEqual(merged([
            "La fonction evaluate calcule la moyenne des récompenses.",
            "La fonction evaluate calcule l'écart-type des récompenses.",
            "La fonction evaluate calcule le minimum.",
            "Le script génère un graphique chart.png.",
            "Le script génère un fichier CSV results.csv.",
            "La classe Server écrit ses journaux.",
            "La classe Server écoute le port 8080.",
        ]), [
            "La fonction evaluate calcule la moyenne des récompenses, l'écart-type des récompenses, le minimum.",
            # Four words alike: one list
            "Le script génère un graphique chart.png, fichier CSV results.csv.",
            # Three only: two facts
            "La classe Server écrit ses journaux.",
            "La classe Server écoute le port 8080.",
        ])
        self.assertEqual(merged(["Un seul fait."]), ["Un seul fait."])

    def test_a_quote_over_several_numbered_lines_is_found(self):
        self.assertIn(normalized("def load(path):\n return json.load(open(path))"),
                      normalized("  1 | def load(path):\n  2 |     return json.load(open(path))"))

    def test_without_sources_nothing_to_be_faithful_to(self):
        judge = ScriptedJudge(claims=["un fait"])
        judgment = judge.judge(sample(sources=False))
        self.assertEqual(judge.asked, ["claims", "rubric"])
        self.assertIsNone(judgment.faithfulness)
        self.assertEqual((judgment.claims[0].verdict, judgment.claims[0].reason), ("unverifiable", NO_SOURCE))

    def test_a_failed_judge_is_told_not_raised(self):
        judgment = ScriptedJudge(fail=True).judge(sample())
        self.assertEqual((judgment.status, judgment.error, judgment.relevance), ("error", "Ollama ne répond pas", None))

    def test_the_event_names_the_sources_without_their_text(self):
        data = ScriptedJudge(claims=["a"]).judge(sample()).to_dict()
        self.assertEqual(data["sources"], [{"tool": "cat_file", "arguments": {"path": "io.py"}, "chars": len(SOURCE)}])
        json.dumps(data)

class FocusTest(unittest.TestCase):
    # A long file, the fact in the middle: what the judge did not find in app/app.py
    LONG: str = "\n".join([f"{i:4} | x_{i} = compute_{i}(value)" for i in range(1, 200)]
                          + ["200 | # The same call made this many times is refused", "201 | SAME_CALLS : int = 2"]
                          + [f"{i:4} | y_{i} = other_{i}()" for i in range(202, 400)])

    def test_exact_names_of_a_claim(self):
        self.assertEqual(names("Un graphique `comparison.png` et results.csv, par evaluate_all_models et maxDepth"),
                         ["comparison.png", "results.csv", "evaluate_all_models", "maxDepth"])
        self.assertEqual(names("La fonction lit le fichier de réglages."), [])
        self.assertEqual(anchors("écrit `results.csv`", ["df.to_csv('results.csv')", "rien"]), [("results.csv", 1)])

    def test_the_window_of_an_exact_name_is_kept_on_top_of_the_others(self):
        # Every window speaks of rewards: the words and the cross-encoder would keep others than the one of the file
        long = "\n".join([f"{i:4} | reward_{i} = rewards.mean() + rewards.std()" for i in range(1, 300)]
                         + ["300 | df.to_csv(os.path.join(runs_dir, 'results.csv'))"])
        claim = "Les rewards (mean, std) sont écrites dans `results.csv`"
        text, = focus([long], [claim], lambda claim, texts: [1.0] + [0.0] * (len(texts) - 1))
        self.assertIn("results.csv", text)
        # The others are still there: the name is on top, never instead
        self.assertIn("reward_", text)

    def test_windows_cover_every_line_and_overlap(self):
        found = windows(["\n".join(str(i) for i in range(31))])
        self.assertEqual([(w.start, w.end) for w in found], [(0, 20), (10, 30), (20, 31)])
        self.assertEqual([(w.start, w.end) for w in windows(["un\ndeux"])], [(0, 2)])

    def test_identifiers_are_cut_in_their_words(self):
        self.assertEqual(terms("SAME_CALLS vaut 2, maxDepth"), ["same", "calls", "vaut", "2", "max", "depth"])

    def test_short_sources_go_whole(self):
        self.assertEqual(focus(["court", "aussi"], ["une affirmation"]), ["court", "aussi"])

    def test_the_passage_of_the_claim_is_found_in_a_long_source(self):
        [text] = focus([self.LONG], ["Le même appel (same call) est refusé après 2 fois : SAME_CALLS"])
        self.assertIn("SAME_CALLS : int = 2", text)
        self.assertLess(len(text), 2500)
        self.assertTrue(text.startswith("[…]"))

    def test_the_cross_encoder_reorders_and_a_broken_one_is_left_out(self):
        # The words alone would pick the windows of the fact: the cross-encoder prefers the first one it is shown
        text, _ = focus([self.LONG, "petite source"], ["SAME_CALLS"], lambda claim, texts: [1.0] + [0.0] * (len(texts) - 1))
        self.assertIn("SAME_CALLS", text)
        def broken(claim, texts):
            raise RuntimeError("pas de fastembed")
        texts = focus([self.LONG, "petite source"], ["SAME_CALLS"], broken)
        self.assertIn("SAME_CALLS : int = 2", texts[0])
        self.assertEqual(texts[1], NOTHING)

class EvaluatorTest(unittest.TestCase):
    def evaluator(self, **settings):
        bus = EventBus()
        scored: list[dict] = []
        bus.subscribe(lambda event: scored.append(event.data), EVAL_SCORED)
        judge = ScriptedJudge(claims=["a"])
        config = {"eval.background": False, "eval.sources": ["cat_file"], **settings}
        return bus, Evaluator(config, bus, judge), judge, scored

    def test_every_answer_judged_when_its_turn_ends(self):
        bus, evaluator, judge, scored = self.evaluator()
        turn(bus)
        self.assertEqual(len(scored), 1)
        self.assertEqual(scored[0]["question"], "La question ?")
        self.assertEqual(evaluator.last().sample.answer, scored[0]["answer"])
        # /eval does not judge it again
        self.assertEqual(judge.asked.count("rubric"), 1)

    def test_off_only_the_last_answer_on_demand(self):
        bus, evaluator, judge, scored = self.evaluator(**{"eval.enabled": False})
        self.assertIsNone(evaluator.last())
        turn(bus, reply="première")
        turn(bus, reply="seconde")
        self.assertEqual(scored, [])
        self.assertEqual(evaluator.last().sample.answer, "seconde")
        self.assertEqual(len(scored), 1)

    def test_in_the_background(self):
        bus, evaluator, judge, scored = self.evaluator(**{"eval.background": True})
        turn(bus)
        self.assertEqual(evaluator.last().status, "ok")
        self.assertEqual(len(scored), 1)

class MetricsTest(unittest.TestCase):
    def judgment(self, faithfulness, relevance, verdicts):
        return {"status": "ok", "faithfulness": faithfulness, "relevance": relevance, "coherence": 5,
                "claims": [{"verdict": verdict} for verdict in verdicts]}

    def test_summary_and_deltas(self):
        summary = summary_of([
            ("code", self.judgment(1.0, 5, ["supported", "supported"])),
            ("code", self.judgment(0.5, 3, ["supported", "contradicted"])),
            ("doc", self.judgment(None, 4, ["unverifiable"])),
            ("doc", None),
        ])
        self.assertEqual(summary["all"]["answered"], 0.75)
        self.assertEqual(summary["all"]["faithfulness"], 0.75)
        self.assertEqual(summary["all"]["sourced"], 2)
        self.assertEqual(summary["all"]["flagged_rate"], 0.4)
        self.assertEqual(summary["all"]["contradicted"], 1)
        self.assertEqual(summary["by_kind"]["doc"]["answered"], 0.5)
        self.assertEqual(deltas({"faithfulness": 0.5, "relevance": None}, {"faithfulness": 0.75, "relevance": 4}),
                         {"faithfulness": 0.25})

    def test_recorded_and_compared_by_version(self):
        path = os.path.join(self.tmp, "traces.jsonl")
        bus = EventBus()
        Recorder(path).bind(bus)
        for prompt in ("v1", "v2"):
            judgment = ScriptedJudge(claims=["a", "b"], verdicts=[
                {"claim": 1, "verdict": "supported", "source": 1, "evidence": ""},
                {"claim": 2, "verdict": "contradicted", "source": 1, "evidence": ""}]).judge(sample())
            judgment.sample.prompt = prompt
            bus.dispatch(EVAL_SCORED, **judgment.to_dict())
        with open(path, encoding="utf-8") as file:
            records = [json.loads(line) for line in file]
        self.assertEqual([r["type"] for r in records], ["eval", "eval"])
        self.assertEqual((records[0]["supported"], records[0]["contradicted"]), (1, 1))
        self.assertEqual(records[0]["flagged"][0]["verdict"], "contradicted")
        stats = eval_stats(records)
        self.assertEqual((stats["answers"], stats["faithfulness"], stats["flagged_rate"]), (2, 0.5, 0.5))
        self.assertEqual([v["prompt"] for v in stats["versions"]], ["v1", "v2"])

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

if __name__ == "__main__":
    unittest.main()
