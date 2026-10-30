##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the tools that read the project and make folders (T4): cat_file, tree, search, mkdir, and the bounds of
## the project they never leave. write_file and edit_file have their own tests, the permissions too
##
import os
from tool.impl.file.tool_cat import CatTool, MAX_LINES
from tool.impl.file.tool_mkdir import MkdirTool
from tool.impl.file.tool_search import SearchTool
from tool.impl.file.tool_tree import TreeTool
from utils.path import resolve_path, display_path

def test_a_path_is_from_the_project_and_never_leaves_it(folder, app, tmp_path):
    root = os.path.realpath(folder)
    assert resolve_path(app, "src/main.py") == os.path.join(root, "src/main.py")
    # "/src/main.py" is the project's, as the tools show it, not the disk's
    assert resolve_path(app, "/src/main.py") == os.path.join(root, "src/main.py")
    assert resolve_path(app, "../outside.txt") is None
    # A link that leads out of the project leads nowhere
    (tmp_path / "secret.txt").write_text("x")
    os.symlink(tmp_path / "secret.txt", folder / "link.txt")
    assert resolve_path(app, "link.txt") is None
    assert display_path(os.path.join(root, "src", "main.py")) == "/src/main.py" and display_path(root) == "/"

def test_cat_shows_the_lines_numbered_and_marks_the_file_seen(folder, app):
    (folder / "main.py").write_text("a = 1\nb = 2\nc = 3\n")
    result = CatTool().handle(app, path="main.py", start_line=2, end_line=3)
    assert result == "/main.py (lignes 2-3 sur 3)\n2 | b = 2\n3 | c = 3"
    # edit_file may now change it
    assert app.seen_files.state(os.path.realpath(folder / "main.py")) == "seen"

def test_cat_reads_a_big_file_by_slices(folder, app):
    (folder / "big.txt").write_text("".join(f"ligne {n}\n" for n in range(1, MAX_LINES + 51)))
    result = CatTool().handle(app, path="big.txt")
    assert f"(lignes 1-{MAX_LINES} sur {MAX_LINES + 50})" in result
    assert result.endswith(f"Suite avec start_line={MAX_LINES + 1}.")

def test_cat_refuses_what_it_can_not_read(folder, app):
    (folder / "src").mkdir()
    (folder / "image.bin").write_bytes(b"\xff\xfe\x00")
    cat = CatTool()
    assert cat.handle(app, path="../x").endswith("en dehors du projet.")
    assert cat.handle(app, path="nope.py").endswith("n'existe pas.")
    assert "est un dossier" in cat.handle(app, path="src")
    assert "pas un fichier texte" in cat.handle(app, path="image.bin")

def test_tree_shows_folders_first_without_the_noise(folder, app):
    for path in ("src/app/app.py", "src/main.py", "README.md", ".git/HEAD", "node_modules/x/index.js", "src/main.pyc"):
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_text("")
    result = TreeTool().handle(app, depth=1)
    assert result.splitlines()[:3] == ["/", "├── src/", "└── README.md"]
    assert "(1 dossiers non développés" in result
    deep = TreeTool().handle(app, path="src", depth=5)
    assert "app.py" in deep and "main.pyc" not in deep and ".git" not in TreeTool().handle(app, depth=5)

def test_search_finds_the_lines_of_a_pattern_by_file_and_glob(folder, app):
    (folder / "src").mkdir()
    (folder / "src/a.py").write_text("def load():\n    return 1\n")
    (folder / "src/b.js").write_text("function load() {}\n")
    search = SearchTool()
    assert search.handle(app, pattern=r"load\(") == "/src/a.py:1: def load():\n/src/b.js:1: function load() {}"
    assert search.handle(app, pattern="load", glob="*.py") == "/src/a.py:1: def load():"
    assert search.handle(app, pattern="(?i)LOAD", path="src/b.js", max_results=1) == "/src/b.js:1: function load() {}"
    assert search.handle(app, pattern="absent").startswith("Aucun résultat")
    assert search.handle(app, pattern="(").startswith("Erreur : expression régulière invalide")

def test_search_tells_when_it_shows_only_part_of_the_results(folder, app):
    (folder / "many.txt").write_text("x\n" * 10)
    result = SearchTool().handle(app, pattern="x", max_results=3)
    assert result.count("/many.txt:") == 3 and "7 résultats de plus" in result

def test_mkdir_asks_then_creates_the_folder_and_its_parents(folder, app):
    assert MkdirTool().handle(app, path="a/b/c") == "OK : dossier /a/b/c créé."
    assert (folder / "a/b/c").is_dir() and app.permissions.asked == ["Création du dossier /a/b/c"]
    # Already there: nothing to ask
    assert MkdirTool().handle(app, path="a/b/c") == "OK : /a/b/c existe déjà."
    assert len(app.permissions.asked) == 1

def test_mkdir_refused_or_out_of_the_project_creates_nothing(folder, app):
    app.permissions.answer = False
    assert MkdirTool().handle(app, path="new").startswith("Refusé")
    assert not (folder / "new").exists()
    assert MkdirTool().handle(app, path="../out").endswith("en dehors du projet.")
    (folder / "file").write_text("")
    assert MkdirTool().handle(app, path="file").startswith("Erreur : 'file' existe déjà, et c'est un fichier.")
