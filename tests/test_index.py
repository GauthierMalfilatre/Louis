##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of rag/index.py: the kinds, the filters, the search inside them, what a source keeps, the migration
##
import os
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from rag.index import Index, Filter, kind_of, path_matches
from rag.chunker import Chunk

class KindTest(unittest.TestCase):
    def test_extensions(self):
        self.assertEqual(kind_of("/src/app.py"), "code")
        self.assertEqual(kind_of("/web/App.TSX"), "code")
        self.assertEqual(kind_of("/docs/guide.md"), "doc")
        self.assertEqual(kind_of("/config/settings.yml"), "config")
        self.assertEqual(kind_of("/data/scores.csv"), "data")
        self.assertEqual(kind_of("/.gitignore"), "data")

    def test_build_files_are_code(self):
        self.assertEqual(kind_of("/Makefile"), "code")
        self.assertEqual(kind_of("/docker/Dockerfile"), "code")

class PathMatchesTest(unittest.TestCase):
    PATH = "/src/auth/UserService.py"

    def test_part_of_the_path(self):
        for pattern in ("src/auth", "auth", "/src/auth/", "userservice", "auth/UserService.py"):
            self.assertTrue(path_matches(self.PATH, pattern), pattern)

    def test_globs(self):
        for pattern in ("src/auth/*", "/src/auth/*", "auth/*", "*.py", "src/*/userservice.py"):
            self.assertTrue(path_matches(self.PATH, pattern), pattern)

    def test_no_match(self):
        for pattern in ("src/api", "docs/*.md", "*.js", "src/auth/*.ts"):
            self.assertFalse(path_matches(self.PATH, pattern), pattern)

    def test_a_folder_glob_does_not_take_its_longer_neighbour(self):
        self.assertFalse(path_matches("/src/auth_v2/login.py", "src/auth/*"))

    def test_empty_pattern_keeps_everything(self):
        self.assertTrue(path_matches(self.PATH, ""))

class FilterTest(unittest.TestCase):
    def test_nothing_on_the_files(self):
        self.assertFalse(Filter().on_files)
        self.assertFalse(Filter(source="api").on_files)
        self.assertTrue(Filter(path="src").on_files)
        self.assertTrue(Filter(kinds=frozenset({"code"})).on_files)
        self.assertTrue(Filter(after=0.0).on_files)

    def test_keeps(self):
        where = Filter(path="src", kinds=frozenset({"code"}), after=100.0)
        self.assertTrue(where.keeps("/src/a.py", 150.0))
        self.assertFalse(where.keeps("/docs/a.py", 150.0))      # path
        self.assertFalse(where.keeps("/src/a.md", 150.0))       # kind
        self.assertFalse(where.keeps("/src/a.py", 50.0))        # too old
        self.assertFalse(where.keeps("/src/a.py", None))        # date unknown: not kept by a date filter
        self.assertTrue(Filter(path="src").keeps("/src/a.py", None))

class IndexTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.index = Index(os.path.join(self.folder.name, "test.rag.db"))
        self.index.begin("api", "/root", None)

    def tearDown(self):
        self.index.close()
        self.folder.cleanup()

    def put(self, path, text, source="api", context="", description=""):
        self.index.put(source, path, "hash-" + path, [Chunk(1, 1, text)], None, [context], [description])

    def search(self, query, where=None):
        return self.index.search(query, None, None, 10, where)

    def test_searching_never_creates_the_file(self):
        path = os.path.join(self.folder.name, "none.rag.db")
        self.assertEqual(Index(path).search("x", None, None, 4), [])
        self.assertFalse(os.path.exists(path))

    def test_keywords_inside_the_filter(self):
        self.put("/src/fuel.py", "def fuel_reward(action): return reward")
        self.put("/docs/fuel.md", "The fuel reward explained")
        self.assertEqual({hit.path for hit in self.search("fuel reward")}, {"/src/fuel.py", "/docs/fuel.md"})
        self.assertEqual([hit.path for hit in self.search("fuel reward", Filter(kinds=frozenset({"code"})))], ["/src/fuel.py"])
        self.assertEqual([hit.path for hit in self.search("fuel reward", Filter(path="docs"))], ["/docs/fuel.md"])
        self.assertEqual(self.search("fuel reward", Filter(path="nowhere")), [])

    def test_sources_apart(self):
        self.index.begin("web", "/web", None)
        self.put("/a.py", "parse the config", source="api")
        self.put("/b.py", "parse the config", source="web")
        self.assertEqual([hit.source for hit in self.search("parse config", Filter(source="web"))], ["web"])

    def test_dates(self):
        self.put("/old.py", "load the model")
        self.put("/new.py", "load the model")
        self.index.stamp("api", {"/old.py": 100.0, "/new.py": 200.0})
        self.assertEqual([hit.path for hit in self.search("load model", Filter(after=150.0))], ["/new.py"])
        self.assertEqual(self.index.span("api"), (100.0, 200.0))
        self.assertEqual(self.search("load model", Filter(path="/new.py"))[0].modified, 200.0)

    def test_context_and_description_are_searched_and_returned(self):
        self.put("/agent.py", "keys = pygame.key.get_pressed()", context="class Human › def run(self)",
                 description="lit les touches du clavier")
        hits = self.search("clavier")
        self.assertEqual([hit.path for hit in hits], ["/agent.py"])
        self.assertEqual(hits[0].context, "class Human › def run(self)")
        self.assertEqual(hits[0].description, "lit les touches du clavier")
        self.assertEqual([hit.path for hit in self.search("run")], ["/agent.py"])

    def test_exclude_and_describe_are_kept_with_the_source(self):
        self.assertEqual(self.index.begin("api", "/root", None, 1, ["tests", " "], True, "small"), (["tests"], True))
        self.assertEqual(self.index.begin("api", "/root", None, 1), (["tests"], True))
        self.assertEqual(self.index.begin("api", "/root", None, 1, [""], False), ([], False))
        self.assertEqual([(s["exclude"], s["describe"]) for s in self.index.sources()], [([], False)])

    def test_a_change_of_chunker_or_describer_reads_every_file_again(self):
        self.put("/a.py", "x = 1")
        self.index.begin("api", "/root", None, 1, None, True, "small")
        self.put("/a.py", "x = 1")
        self.index.begin("api", "/root", None, 1, None, True, "small")
        self.assertEqual(self.index.files("api")["/a.py"][0], "hash-/a.py")     # nothing changed: kept
        self.index.begin("api", "/root", None, 1, None, True, "big")
        self.assertEqual(self.index.files("api")["/a.py"][0], "")               # another describer: read again
        self.put("/a.py", "x = 1")
        self.index.begin("api", "/root", None, 2, None, True, "big")
        self.assertEqual(self.index.files("api")["/a.py"][0], "")               # another chunker: read again

    def test_description_cache(self):
        self.assertIsNone(self.index.described("key"))
        self.index.remember("api", "key", "sauvegarde le modèle")
        self.assertEqual(self.index.described("key"), "sauvegarde le modèle")
        self.index.forget("api")
        self.assertIsNone(self.index.described("key"))

    def test_outline(self):
        self.put("/src/a.py", "a")
        self.put("/src/b.py", "b")
        self.put("/README.md", "readme")
        outline = self.index.outline("api")
        self.assertEqual(outline["folders"], [("src", 2), (".", 1)])
        self.assertEqual(outline["kinds"], {"code": 2, "doc": 1})

class MigrationTest(unittest.TestCase):
    def test_an_old_index_gets_the_new_columns_and_keeps_its_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "old.rag.db")
            db = sqlite3.connect(path)
            db.executescript("""
                CREATE TABLE sources (name TEXT PRIMARY KEY, root TEXT NOT NULL, model TEXT, updated_at TEXT NOT NULL);
                CREATE TABLE files (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, path TEXT NOT NULL,
                                    hash TEXT NOT NULL, embedded INTEGER NOT NULL DEFAULT 0, UNIQUE (source, path));
                CREATE TABLE chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, file_id INTEGER NOT NULL, start_line INTEGER,
                                     end_line INTEGER, text TEXT NOT NULL, vector BLOB);
                INSERT INTO sources VALUES ('api', '/root', NULL, 'now');
                INSERT INTO files (source, path, hash) VALUES ('api', '/a.py', 'h');
            """)
            db.commit()
            db.close()
            index = Index(path)
            columns = lambda table: {row["name"] for row in index._Index__open().execute(f"PRAGMA table_info({table})")}
            self.assertTrue({"exclude", "chunker", "describe", "describer"} <= columns("sources"))
            self.assertIn("modified", columns("files"))
            self.assertTrue({"context", "description"} <= columns("chunks"))
            self.assertEqual(index.files("api"), {"/a.py": ("h", False)})
            index.close()

if __name__ == "__main__":
    unittest.main()
