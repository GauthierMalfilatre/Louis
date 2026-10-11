##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the risk of the tool calls: what each would do, judged before it runs, and whether it can be undone
##
import pytest
import utils.path
from conftest import git
from tool.impl.file.tool_cat import CatTool
from tool.impl.file.tool_edit import EditTool
from tool.impl.file.tool_mkdir import MkdirTool
from tool.impl.file.tool_write import WriteTool
from tool.impl.git import tool_git
from tool.impl.git.tool_git import GitTool
from tool.impl.git.tool_pr import PullRequestTool
from tool.risk import Risk, NONE, SAFE, REVERSIBLE, IRREVERSIBLE

@pytest.fixture(autouse=True)
def git_root(folder, monkeypatch):
    """
        The git tool runs in the project the test made, as the file tools do: after folder, which moves the root
        there. Before it, the git tool would read the repository of Louis itself
    """
    monkeypatch.setattr(tool_git, "ROOT", utils.path.ROOT)

def test_the_levels_go_from_safe_to_irreversible():
    assert Risk(IRREVERSIBLE).at_least(REVERSIBLE) and Risk(REVERSIBLE).at_least(REVERSIBLE)
    assert not Risk(REVERSIBLE).at_least(IRREVERSIBLE) and NONE.level == SAFE

def test_a_tool_that_reads_changes_nothing(folder, app):
    (folder / "a.py").write_text("x = 1\n")
    assert CatTool().risk(app, path="a.py") == NONE

def test_a_new_file_or_folder_can_be_removed_again(folder, app):
    risk: Risk = WriteTool().risk(app, path="new.py", content="x = 1\n")
    assert (risk.level, risk.consequence, risk.undo) == (REVERSIBLE, "/new.py sera créé", "supprimer /new.py")
    # What the plan shows of it: the lines the file would hold
    assert "+x = 1" in risk.preview
    assert MkdirTool().risk(app, path="docs").level == REVERSIBLE
    # Judged only: nothing is written, nobody is asked
    assert not (folder / "new.py").exists() and not (folder / "docs").exists() and app.permissions.asked == []

def test_a_committed_file_can_be_restored_by_git(repo, app):
    risk: Risk = WriteTool().risk(app, path="README.md", content="# Autre\n", overwrite=True)
    assert (risk.level, risk.undo) == (REVERSIBLE, "git restore README.md")
    assert EditTool().risk(app, path="README.md", old_str="Projet", new_str="Louis").level == REVERSIBLE

@pytest.mark.parametrize("change", ["modified", "untracked"])
def test_a_file_git_does_not_have_as_it_is_is_lost(repo, app, change):
    if change == "modified":
        (repo / "README.md").write_text("# Projet changé\n")
        path = "README.md"
    else:
        (repo / "notes.txt").write_text("à garder\n")
        path = "notes.txt"
    risk: Risk = WriteTool().risk(app, path=path, content="x", overwrite=True)
    assert (risk.level, risk.undo) == (IRREVERSIBLE, "")
    assert EditTool().risk(app, path=path, old_str="x", new_str="y").level == IRREVERSIBLE

def test_outside_a_repository_a_replaced_file_is_lost(folder, app):
    (folder / "a.py").write_text("x = 1\n")
    assert WriteTool().risk(app, path="a.py", content="x = 2\n", overwrite=True).level == IRREVERSIBLE

@pytest.mark.parametrize("tool, arguments", [
    (WriteTool(), {"path": "a.py", "content": "x"}),            # exists, no overwrite: the tool refuses
    (WriteTool(), {"path": "../out.py", "content": "x"}),       # outside the project
    (EditTool(), {"path": "missing.py", "old_str": "a", "new_str": "b"}),
    (MkdirTool(), {"path": "a.py"}),                            # already there
])
def test_a_call_the_tool_refuses_changes_nothing(folder, app, tool, arguments):
    (folder / "a.py").write_text("x = 1\n")
    assert tool.risk(app, **arguments) == NONE

@pytest.mark.parametrize("arguments, level", [
    ({"action": "status"}, SAFE),
    ({"action": "log"}, SAFE),
    ({"action": "branch", "branch": "feat/x"}, REVERSIBLE),
    ({"action": "checkout", "branch": "feat/x"}, REVERSIBLE),   # the git command small models write
    ({"action": "pull"}, REVERSIBLE),
    ({"action": "commit", "paths": ["README.md"], "message": "m"}, REVERSIBLE),
    ({"action": "push"}, IRREVERSIBLE),
    ({"action": "delete_branch", "branch": "feat/x"}, IRREVERSIBLE),
    ({"action": "rebase"}, SAFE),                               # refused by the tool
])
def test_the_git_actions_that_reach_origin_or_delete_can_not_be_undone(repo, app, arguments, level):
    assert GitTool().risk(app, **arguments).level == level

def test_a_git_risk_names_the_branch(repo, app):
    git(repo, "switch", "-q", "-c", "feat/y")
    assert "feat/y" in GitTool().risk(app, action="push").consequence

@pytest.mark.parametrize("arguments, level", [
    ({"action": "list"}, SAFE),
    ({"action": "view", "number": 3}, SAFE),
    ({"action": "create", "title": "t", "head": "feat/x", "base": "dev"}, IRREVERSIBLE),
    ({"action": "comment", "number": 3, "body": "ok"}, IRREVERSIBLE),
    ({"action": "merge", "number": 3}, IRREVERSIBLE),
])
def test_what_is_said_or_merged_on_github_can_not_be_undone(repo, app, arguments, level):
    assert PullRequestTool().risk(app, **arguments).level == level

def test_the_preview_shows_what_would_change(repo, app):
    risk: Risk = EditTool().risk(app, path="README.md", old_str="# Projet", new_str="# Louis")
    assert "-# Projet" in risk.preview and "+# Louis" in risk.preview
    replaced: Risk = WriteTool().risk(app, path="README.md", content="# Autre\n", overwrite=True)
    assert "-# Projet" in replaced.preview and "+# Autre" in replaced.preview
    commit: Risk = GitTool().risk(app, action="commit", paths=["README.md"], message="docs: titre")
    assert commit.preview == "docs: titre\n  README.md"
    assert "Titre" in PullRequestTool().risk(app, action="create", title="Titre", body="Corps").preview
