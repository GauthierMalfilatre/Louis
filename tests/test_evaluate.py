##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of rag/evaluate.py: how an expected passage is read and found, and the metrics
##
import os
import sys
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from rag.evaluate import Expected, Result, parse_expected, matches, rank_of, summarize, thresholds
from rag.index import Hit

def hit(path, start, end, score=0.5):
    return Hit("demo", path, start, end, "", score)

def result(rank, deep_rank, answer_score, answerable=True, top_score=0.5, kind="concept"):
    return Result("q", kind, answerable, rank, deep_rank, answer_score, top_score, 4 if answerable else 0, [])

class ExpectedTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_expected("src/app.py:10-40"), Expected("/src/app.py", 10, 40))
        self.assertEqual(parse_expected("/src/app.py"), Expected("/src/app.py", None, None))

    def test_a_passage_overlapping_the_lines_matches(self):
        expected = Expected("/a.py", 10, 20)
        self.assertTrue(matches(hit("/a.py", 1, 10), expected))
        self.assertTrue(matches(hit("/a.py", 15, 30), expected))
        self.assertFalse(matches(hit("/a.py", 21, 30), expected))
        self.assertFalse(matches(hit("/b.py", 10, 20), expected))
        self.assertTrue(matches(hit("/a.py", 500, 600), Expected("/a.py", None, None)))

    def test_rank_of_the_first_right_passage(self):
        hits = [hit("/b.py", 1, 5), hit("/a.py", 1, 5), hit("/a.py", 6, 9)]
        self.assertEqual(rank_of(hits, [Expected("/a.py", None, None)]), 2)
        self.assertIsNone(rank_of(hits, [Expected("/c.py", None, None)]))

class MetricsTest(unittest.TestCase):
    def test_summary(self):
        summary = summarize([result(1, 1, 0.9), result(None, 8, 0.2), result(None, None, None),
                             result(None, None, None, answerable=False, top_score=0.03)], 4)
        self.assertEqual(summary["answerable"]["questions"], 3)
        self.assertEqual(summary["answerable"]["hit@1"], round(1 / 3, 3))
        self.assertEqual(summary["answerable"]["hit@20"], round(2 / 3, 3))
        self.assertEqual(summary["answerable"]["mrr"], round((1 + 1 / 8) / 3, 3))
        self.assertEqual(summary["unanswerable"]["questions"], 1)

    def test_thresholds(self):
        rows = {row["min_score"]: row for row in thresholds(
            [result(1, 1, 0.9), result(2, 2, 0.04), result(None, None, None, answerable=False, top_score=0.03)], 4)}
        self.assertEqual((rows[0.01]["hit@4"], rows[0.01]["noise_silenced"]), (1.0, 0.0))
        self.assertEqual((rows[0.05]["hit@4"], rows[0.05]["noise_silenced"]), (0.5, 1.0))

if __name__ == "__main__":
    unittest.main()
