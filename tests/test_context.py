##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of rag/context.py: where a passage is in its file
##
import os
import sys
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from rag.chunker import Chunk
from rag.context import contexts, header, brief

PYTHON = '''import os

class Trainer:
    """ Train an agent """

    def __init__(self, episodes=100):
        self.episodes = episodes

    def run(self, render=False):
        """ Train until the task is solved """
        for episode in range(self.episodes):
            self.step()
        return True

    def step(self):
        pass

def main():
    Trainer().run()
'''

class PythonTest(unittest.TestCase):
    def test_the_definitions_a_passage_is_in(self):
        found = contexts("/train.py", PYTHON, [Chunk(11, 13, "")])[0]
        self.assertTrue(found.startswith("class Trainer › def run(self, render=False)"), found)
        self.assertIn("— Train until the task is solved", found)

    def test_the_definitions_starting_in_a_passage(self):
        found = contexts("/train.py", PYTHON, [Chunk(12, 20, "")])[0]
        self.assertIn("class Trainer › def run", found)
        self.assertIn("[def step, def main]", found)

    def test_the_methods_of_a_class_starting_in_it_are_not_listed(self):
        # Lines 1-8 hold the class and its first method: the class only is named, its method is its business
        self.assertEqual(contexts("/train.py", PYTHON, [Chunk(1, 8, "")])[0], "[class Trainer] — Train an agent")

    def test_a_file_that_does_not_parse_falls_back_on_indentation(self):
        broken = "def run(self):\n    x = (\n    return x\n"
        self.assertEqual(contexts("/broken.py", broken, [Chunk(3, 3, "")]), ["def run(self)"])

class OtherFilesTest(unittest.TestCase):
    def test_markdown_titles(self):
        text = "# Guide\n\n## Install\n\n```\n# not a title\n```\n\n### Linux\n\napt install x\n"
        self.assertEqual(contexts("/README.md", text, [Chunk(1, 2, ""), Chunk(11, 11, "")]),
                         ["", "Guide › Install › Linux"])

    def test_yaml_top_level_key(self):
        text = "production:\n  debug: false\n  workers: 4\nstaging:\n  debug: true\n"
        self.assertEqual(contexts("/config.yml", text, [Chunk(2, 3, ""), Chunk(5, 5, "")]), ["production", "staging"])

    def test_c_function(self):
        text = "#include <stdio.h>\n\nstatic int add(int a, int b)\n{\n    int s = a + b;\n    if (s > 0) {\n        return s;\n    }\n    return 0;\n}\n"
        self.assertEqual(contexts("/math.c", text, [Chunk(7, 7, "")]), ["static int add(int a, int b)"])

    def test_javascript_method(self):
        text = "export class Store {\n  async load(url) {\n    const r = await fetch(url);\n    return r.json();\n  }\n}\n"
        self.assertEqual(contexts("/store.js", text, [Chunk(3, 4, "")]), ["export class Store › async load(url)"])

    def test_nothing_known_of_a_text(self):
        self.assertEqual(contexts("/notes.txt", "a\nb\n", [Chunk(1, 2, "")]), [""])

class FormatTest(unittest.TestCase):
    def test_header(self):
        self.assertEqual(header("/src/train.py", "class Trainer › def run(self)"), "src/train.py › class Trainer › def run(self)")
        self.assertEqual(header("/src/train.py", ""), "src/train.py")

    def test_brief_drops_the_arguments_and_the_list(self):
        self.assertEqual(brief("class Trainer › def run(self, render=f(x)) [def step, def main] — Train"),
                         "class Trainer › def run — Train")

if __name__ == "__main__":
    unittest.main()
