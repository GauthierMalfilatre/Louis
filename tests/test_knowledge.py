##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of rag/knowledge.py and of the tool search_knowledge: reranking, threshold, filters, indexing, descriptions.
## No model is called: the reranker and the describer are fakes, and there are no vectors (keywords only)
##
import os
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from events.event_bus import EventBus
from rag.describer import DescribeError
from rag.index import Index
from rag.knowledge import Knowledge, day, since
from rag.reranker import RerankError
from tool.impl.rag.tool_knowledge import KnowledgeTool

FILES = {
    "src/fuel.py": "def fuel_reward(action, reward, fuel):\n    fuel -= 10\n    return reward - 0.01, fuel\n",
    "src/agent.py": "class Agent:\n    def run(self):\n        keys = pygame.key.get_pressed()\n        return keys\n",
    "docs/guide.md": "# Guide\n\n## Fuel\n\nThe fuel reward lowers the reward of each engine.\n",
    "tests/test_fuel.py": "def test_fuel_reward():\n    assert fuel_reward(1, 0, 10)\n",
    "config/grid.yml": "\n".join(["run-%d:" % (i % 3), "  lr: 0.1", "  fuel: false"][i % 3] for i in range(900)),
}

class FakeReranker:
    """ Scores 0.9 a passage holding the word "fuel", 0.01 the others """
    model, pool, min_score = "fake", 20, 0.05

    def score(self, query, texts):
        return [0.9 if "fuel" in text.lower() else 0.01 for text in texts]

class BrokenReranker(FakeReranker):
    def score(self, query, texts):
        raise RerankError("not installed")

class FakeDescriber:
    model = "fake-describer"

    def __init__(self, fail=False):
        self.calls, self.fail = 0, fail

    def describe(self, path, outline, lines, context, text):
        if self.fail:
            raise DescribeError("Ollama ne répond pas")
        self.calls += 1
        return f"décrit {path}:{lines[0]}"

class KnowledgeTestCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.folder.name, "project")
        for path, text in FILES.items():
            os.makedirs(os.path.dirname(os.path.join(self.root, path)), exist_ok=True)
            with open(os.path.join(self.root, path), "w") as file:
                file.write(text)
        self.events = []
        self.bus = EventBus().subscribe(lambda event: self.events.append((event.name, event.data)))
        self.index = Index(os.path.join(self.folder.name, "test.rag.db"))

    def tearDown(self):
        self.index.close()
        self.folder.cleanup()

    def knowledge(self, reranker=None, describer=None):
        return Knowledge(self.bus, self.index, None, 4, reranker, 0.10, describer)

    def last(self, name):
        return [data for event, data in self.events if event == name][-1]

class IndexingTest(KnowledgeTestCase):
    def test_generated_and_excluded_files_are_left_out(self):
        result = self.knowledge().index(self.root, "demo", exclude=["tests"])
        self.assertEqual(result["excluded"], 1)
        self.assertEqual([item["path"] for item in result["generated"]], ["/config/grid.yml"])
        self.assertEqual(set(self.index.files("demo")), {"/src/fuel.py", "/src/agent.py", "/docs/guide.md"})
        # The patterns are kept: the next /index applies them without being given them
        self.assertEqual(self.knowledge().index(self.root, "demo")["exclude"], ["tests"])

    def test_the_files_are_dated(self):
        self.knowledge().index(self.root, "demo")
        self.assertIsNotNone(self.index.span("demo"))
        self.assertIn("modifiés du", self.knowledge().catalog())

    def test_descriptions_of_the_code_only_and_kept(self):
        describer = FakeDescriber()
        result = self.knowledge(describer=describer).index(self.root, "demo", describe=True)
        self.assertEqual(result["described"], 3)        # the code: fuel.py, agent.py, test_fuel.py; not the guide
        self.assertEqual(self.knowledge(describer=describer).index(self.root, "demo")["described"], 0)
        # Off then on again: everything from the cache, the model is not asked again
        self.knowledge(describer=describer).index(self.root, "demo", describe=False)
        result = self.knowledge(describer=describer).index(self.root, "demo", describe=True)
        self.assertEqual((result["described"], result["reused"], describer.calls), (0, 3, 3))

    def test_a_file_left_short_is_described_by_the_next_indexing(self):
        result = self.knowledge(describer=FakeDescriber(fail=True)).index(self.root, "demo", describe=True)
        self.assertIsNotNone(result["describe_warning"])
        self.assertEqual(self.index.files("demo")["/src/fuel.py"][0], "")       # no hash: read again next time
        result = self.knowledge(describer=FakeDescriber()).index(self.root, "demo")
        self.assertEqual(result["described"], 3)

class SearchTest(KnowledgeTestCase):
    def setUp(self):
        super().setUp()
        self.knowledge(describer=None).index(self.root, "demo", exclude=["tests"])

    def test_the_threshold_drops_the_near_misses(self):
        found = self.knowledge(FakeReranker()).search("reward of the engines", "demo")
        self.assertTrue(found.hits)
        self.assertTrue(all("fuel" in hit.text.lower() for hit in found.hits))
        self.assertTrue(all(hit.fused is not None for hit in found.hits))
        event = self.last("rag.retrieved")
        self.assertEqual(event["reranker"], "fake")
        self.assertEqual(event["dropped"], found.candidates - len(found.hits))

    def test_nothing_answers(self):
        found = self.knowledge(FakeReranker()).search("pygame keys", "demo", path="src/agent.py")
        self.assertEqual(found.hits, [])
        self.assertGreater(found.candidates, 0)
        self.assertGreater(len(self.knowledge(FakeReranker()).search("pygame keys", "demo", drop=False).hits), 0)

    def test_a_broken_reranker_keeps_the_order_of_the_index(self):
        found = self.knowledge(BrokenReranker()).search("reward", "demo")
        self.assertTrue(found.hits)
        self.assertIsNone(self.last("rag.retrieved")["reranker"])

    def test_filters(self):
        knowledge = self.knowledge()
        self.assertEqual({hit.path for hit in knowledge.search("fuel reward", "demo", kind="doc").hits}, {"/docs/guide.md"})
        self.assertEqual(knowledge.search("fuel reward", "demo", path="nowhere").files, 0)
        self.assertEqual(knowledge.search("fuel reward", "demo", after="2999-01-01").files, 0)
        self.assertEqual(knowledge.search("fuel reward", "demo", after="2000-01-01").files, 3)
        with self.assertRaises(ValueError):
            knowledge.search("fuel", "demo", after="last week")

    def test_dates(self):
        self.assertEqual(day(since("2026-09-30")), "2026-09-30")

class ToolTest(KnowledgeTestCase):
    def setUp(self):
        super().setUp()
        self.knowledge(describer=None).index(self.root, "demo", exclude=["tests"])
        self.tool = KnowledgeTool()

    def handle(self, reranker=None, **arguments):
        app = type("App", (), {"knowledge": self.knowledge(reranker)})()
        return self.tool.handle(app, **arguments)

    def test_passages(self):
        result = self.handle(query="fuel reward", source="demo", kind="code")
        self.assertTrue(result.startswith("[1] demo /src/fuel.py:1-3 (def fuel_reward(action, reward, fuel))"), result)
        self.assertIn("· modifié le ", result.splitlines()[0])

    def test_a_wrong_folder_shows_the_folders(self):
        result = self.handle(query="fuel", source="demo", path="lib")
        self.assertTrue(result.startswith("Erreur : aucun fichier ne correspond à path='lib'"))
        self.assertIn("src", result)

    def test_bad_arguments(self):
        self.assertIn("'kind' doit être", self.handle(query="fuel", kind="python"))
        self.assertIn("'modified_after' doit être une date", self.handle(query="fuel", modified_after="hier"))
        self.assertIn("n'existe pas", self.handle(query="fuel", source="other"))

    def test_nothing_answers_with_and_without_a_filter(self):
        self.assertIn("ne couvre pas ce sujet", self.handle(FakeReranker(), query="pygame keys", source="demo"))
        self.assertIn("trop étroit", self.handle(FakeReranker(), query="pygame keys", source="demo", path="src/agent.py"))

    def test_the_catalog_in_the_description(self):
        self.tool.refresh(self.knowledge().catalog())
        self.assertIn("Sources indexées :\n- demo (3 fichiers", self.tool.desc)

if __name__ == "__main__":
    unittest.main()
