##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## The write_file tool: files it creates, those it never replaces unasked, and the strings small models cut
##
from tool.impl.file.tool_write import WriteTool, fix_newlines

def write(app, **arguments) -> str:
    return WriteTool().handle(app, **arguments)

def test_creates_a_file_and_its_missing_folders(folder, app):
    assert write(app, path="src/game/main.py", content="print('hi')\n").startswith("OK : /src/game/main.py créé")
    assert (folder / "src/game/main.py").read_text() == "print('hi')\n"

def test_an_existing_file_is_replaced_only_when_asked(folder, app):
    (folder / "notes.md").write_text("old\n")
    assert write(app, path="notes.md", content="new\n").startswith("Erreur : 'notes.md' existe déjà")
    # Some models send booleans as text
    assert write(app, path="notes.md", content="new\n", overwrite="true").startswith("OK : /notes.md remplacé")
    assert (folder / "notes.md").read_text() == "new\n"

def test_a_write_the_user_refuses_creates_nothing(folder, app):
    app.permissions.answer = False
    assert write(app, path="a.txt", content="a\n").startswith("Refusé")
    assert not (folder / "a.txt").exists()

def test_files_outside_the_project_are_out_of_reach(folder, app):
    assert write(app, path="../outside.txt", content="x").endswith("est en dehors du projet.")

def test_a_python_string_cut_by_a_newline_is_joined_again():
    # The \n of a string, written by the model as a real newline in the JSON of its call
    assert fix_newlines("a.py", "print('a\nb')\n") == "print('a\\nb')\n"
    # Valid code, and other files, are kept as they are
    assert fix_newlines("a.py", "s = '''a\nb'''\n") == "s = '''a\nb'''\n"
    assert fix_newlines("a.txt", "print('a\nb')\n") == "print('a\nb')\n"
