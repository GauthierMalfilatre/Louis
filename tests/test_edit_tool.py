##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## The edit_file tool: the edits it applies, the mistakes of small models it repairs, and those it refuses
##
import os
import pytest
from tool.impl.file.tool_edit import EditTool

CODE = "def f():\n    a = 1\n    return a\n"

@pytest.fixture
def code(folder, app):
    """ A Python file the model has read: edit_file needs it to be """
    path = folder / "main.py"
    path.write_text(CODE)
    app.seen_files.mark(os.path.realpath(path))
    return path

def edit(app, **arguments) -> str:
    return EditTool().handle(app, **{"path": "main.py", **arguments})

def test_replaces_the_passage_and_shows_it(code, app):
    result: str = edit(app, old_str="    a = 1", new_str="    a = 2")
    assert result.startswith("OK : 1 occurrence remplacée dans /main.py.")
    assert "    2 |     a = 2" in result
    assert code.read_text() == CODE.replace("a = 1", "a = 2")

def test_the_file_must_be_read_before_it_is_edited(folder, app):
    (folder / "main.py").write_text(CODE)
    assert edit(app, old_str="a = 1", new_str="a = 2").startswith("Erreur : lis d'abord 'main.py'")

def test_a_file_changed_since_it_was_read_must_be_read_again(code, app):
    code.write_text(CODE + "# changed by the user\n")
    assert "a changé depuis ta dernière lecture" in edit(app, old_str="a = 1", new_str="a = 2")

def test_line_numbers_copied_from_cat_file_are_left_out(code, app):
    assert edit(app, old_str="   2 |     a = 1", new_str="   2 |     a = 3").startswith("OK")
    assert "    a = 3\n" in code.read_text()

def test_newlines_escaped_once_too_many_are_repaired(code, app):
    assert edit(app, old_str="    a = 1\\n    return a", new_str="    a = 4\\n    return a").startswith("OK")
    assert "    a = 4\n    return a\n" in code.read_text()

def test_a_passage_found_twice_needs_replace_all(code, app):
    code.write_text("x = 0\nx = 0\n")
    app.seen_files.mark(os.path.realpath(code))
    assert edit(app, old_str="x = 0", new_str="x = 1").startswith("Erreur : 'old_str' apparaît 2 fois")
    assert edit(app, old_str="x = 0", new_str="x = 1", replace_all=True).startswith("OK : 2 occurrences")
    assert code.read_text() == "x = 1\nx = 1\n"

def test_a_passage_not_in_the_file_shows_the_closest_one(code, app):
    result: str = edit(app, old_str="    a = 10", new_str="    a = 2")
    assert result.startswith("Erreur : 'old_str' introuvable") and "Le passage le plus proche" in result
    assert code.read_text() == CODE

def test_an_edit_that_breaks_python_is_never_applied(code, app):
    assert "casserait la syntaxe" in edit(app, old_str="    return a", new_str="    return (a")
    assert code.read_text() == CODE

def test_an_edit_that_changes_nothing_is_an_error(code, app):
    result: str = edit(app, old_str="    a = 1", new_str="    a = 1")
    assert result.startswith("Erreur") and "identiques" in result

def test_an_edit_the_user_refuses_changes_nothing(code, app):
    app.permissions.answer = False
    assert edit(app, old_str="    a = 1", new_str="    a = 2").startswith("Refusé")
    assert code.read_text() == CODE

def test_files_outside_the_project_are_out_of_reach(code, app):
    assert edit(app, path="../outside.py", old_str="a", new_str="b").endswith("est en dehors du projet.")
