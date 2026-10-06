##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of rag/describer.py: what is asked to Ollama, and what is kept of its answer (Ollama is not called)
##
import os
import sys
import unittest
from unittest import mock
import requests
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from rag.describer import Describer, DescribeError, clean, MOST_CHARS

def answer(status: int, content: str = "") -> mock.Mock:
    return mock.Mock(status_code=status, json=lambda: {"message": {"content": content}})

class CleanTest(unittest.TestCase):
    def test_one_line_without_markup(self):
        self.assertEqual(clean("**Lit** les `touches`\n du clavier.\n\nMots-clés : keyboard"),
                         "Lit les touches du clavier. Mots-clés : keyboard")

    def test_thinking_is_dropped(self):
        self.assertEqual(clean("<think>let me see\nhmm</think>\nSauvegarde le modèle."), "Sauvegarde le modèle.")

    def test_cut(self):
        self.assertEqual(len(clean("mot " * 500)), MOST_CHARS)

class DescribeTest(unittest.TestCase):
    def setUp(self):
        self.describer = Describer("http://ollama", "small:4b", 4096, "30m", 80)

    def test_the_request(self):
        with mock.patch("rag.describer.requests.post", return_value=answer(200, "Lit les touches du clavier.")) as post:
            text = self.describer.describe("/agent.py", "- class Human", (10, 20), "class Human › def run", "keys = get()")
        self.assertEqual(text, "Lit les touches du clavier.")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "small:4b")
        self.assertIs(payload["think"], False)
        self.assertEqual(payload["options"]["num_ctx"], 4096)
        self.assertEqual(payload["options"]["num_predict"], 80)
        # The instructions first, the same for every request; in the prompt, the file before the passage
        prompt = payload["messages"][1]["content"]
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertLess(prompt.index("Plan du fichier"), prompt.index("keys = get()"))

    def test_the_model_is_not_downloaded(self):
        with mock.patch("rag.describer.requests.post", return_value=answer(404)):
            with self.assertRaises(DescribeError) as raised:
                self.describer.describe("/a.py", "", (1, 1), "", "x")
        self.assertIn("ollama pull small:4b", raised.exception.message)

    def test_ollama_is_stopped(self):
        with mock.patch("rag.describer.requests.post", side_effect=requests.ConnectionError()):
            with self.assertRaises(DescribeError):
                self.describer.describe("/a.py", "", (1, 1), "", "x")

if __name__ == "__main__":
    unittest.main()
