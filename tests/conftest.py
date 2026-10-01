##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Fixtures of the tests: a project folder the tools work in, its git repository, and what they use of the app
##
import os
import subprocess
import pytest
import utils.path
from tool.seen_files import SeenFiles

COAUTHOR = "Louis <louis@example.com>"

class Permissions:
    """ Gives answer to every request, and keeps what was asked: the user, without a terminal """
    def __init__(self, answer: bool = True):
        self.answer: bool = answer
        self.asked: list[str] = []

    def request(self, tool: str, summary: str, preview: str = "", *, every_time: bool = False) -> bool:
        self.asked.append(summary)
        return self.answer

class FakeApp:
    """ What the tools use of the app """
    def __init__(self):
        self.settings: dict = {"git.coauthor": COAUTHOR}
        self.permissions: Permissions = Permissions()
        self.seen_files: SeenFiles = SeenFiles()
        self.knowledge = None

def git(cwd, *args: str) -> str:
    """ Run git in cwd, as the user would: the state a test starts from, or what it checks after """
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()

@pytest.fixture
def app() -> FakeApp:
    return FakeApp()

@pytest.fixture
def folder(tmp_path, monkeypatch):
    """ The project the tools work in: the folder Louis started in, found when they are imported """
    work = tmp_path / "work"
    work.mkdir()
    root: str = os.path.realpath(work)
    monkeypatch.chdir(root)
    monkeypatch.setattr(utils.path, "ROOT", root)
    return work

@pytest.fixture
def project(folder, tmp_path):
    """ The project as a git repository with no commit yet, and its origin: a bare repository beside it """
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(folder, "init", "-q", "-b", "main")
    # In the repository only: the global config of whoever runs the tests (signed commits...) stays out
    for key, value in (("user.name", "Tester"), ("user.email", "tester@example.com"), ("commit.gpgsign", "false")):
        git(folder, "config", key, value)
    git(folder, "remote", "add", "origin", str(origin))
    return folder

@pytest.fixture
def repo(project):
    """ The project with a first commit on main, pushed, and a dev branch that only origin has """
    (project / "README.md").write_text("# Projet\n")
    git(project, "add", "README.md")
    git(project, "commit", "-q", "-m", "init")
    git(project, "push", "-q", "-u", "origin", "main")
    git(project, "push", "-q", "origin", "main:dev")
    return project
