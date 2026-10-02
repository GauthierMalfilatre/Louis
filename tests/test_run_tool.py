##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## The run_code tool: what it refuses before running anything, and what the sandbox lets the code do
##
import pytest
from tool.impl.exec import tool_run
from tool.impl.exec.tool_run import RunTool, Capture, sandbox

def run_code(app, **arguments) -> str:
    return RunTool().handle(app, **arguments)

def image_ready(image: str) -> bool:
    """ Whether docker works here and has the image: the real tests need both, and CI may have neither """
    return tool_run.available() and tool_run.image_problem(image) is None

needs_python = pytest.mark.skipif(not image_ready("python:3.13-alpine"), reason="docker or python:3.13-alpine missing")
needs_sh = pytest.mark.skipif(not image_ready("alpine:latest"), reason="docker or alpine:latest missing")

@pytest.fixture
def no_docker_call(monkeypatch):
    """ Docker answers that the image is there, and nothing is started: for what is decided before the container """
    monkeypatch.setattr(tool_run, "image_problem", lambda image: None)
    def fail(*args, **kwargs):
        raise AssertionError("a container was started")
    monkeypatch.setattr(tool_run.subprocess, "Popen", fail)

def test_arguments_that_do_not_exist_are_refused(app, no_docker_call):
    assert run_code(app, language="python", code="print(1)", network=True).startswith("Erreur : network n'existe pas")

def test_language_and_code_are_required(app, no_docker_call):
    assert run_code(app, language="python").startswith("Erreur : 'language' et 'code' sont requis")
    assert run_code(app, language="python", code="  \n").startswith("Erreur : 'language' et 'code' sont requis")
    assert run_code(app, language=3, code="print(1)").startswith("Erreur : 'language' et 'code' sont requis")

def test_a_language_the_tool_does_not_have_is_refused(app, no_docker_call):
    assert run_code(app, language="cobol", code="x").startswith("Erreur : le langage 'cobol' n'est pas disponible")

def test_code_too_long_for_the_pipe_is_refused(app, no_docker_call):
    assert "trop long" in run_code(app, language="python", code="#" * (tool_run.MAX_CODE + 1))

def test_the_user_reads_the_code_before_it_runs(app, no_docker_call):
    app.permissions.answer = False
    assert run_code(app, language="python", code="print(1)").startswith("Refusé")
    assert app.permissions.asked == ["Exécution de code python dans un conteneur isolé"]

def test_a_missing_image_is_reported_before_asking_the_user(app, monkeypatch):
    monkeypatch.setattr(tool_run, "run", lambda *args, **kwargs: (False, "Error response from daemon: No such image: x"))
    assert "docker pull python:3.13-alpine" in run_code(app, language="python", code="print(1)")
    assert app.permissions.asked == []

def test_a_docker_that_does_not_answer_is_reported(app, monkeypatch):
    monkeypatch.setattr(tool_run, "run", lambda *args, **kwargs: (False, "Cannot connect to the Docker daemon"))
    assert run_code(app, language="sh", code="echo 1").startswith("Erreur : docker ne répond pas")

def test_the_model_names_of_a_language_are_understood(app, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(tool_run, "image_problem", lambda image: seen.append(image) or "Erreur : stop")
    run_code(app, language="Bash", code="echo 1")
    run_code(app, language="python3", code="print(1)")
    assert seen == ["alpine:latest", "python:3.13-alpine"]

def test_settings_give_another_image(app, monkeypatch):
    app.settings["sandbox.images"] = {"python": "python:3.12-slim"}
    seen: list[str] = []
    monkeypatch.setattr(tool_run, "image_problem", lambda image: seen.append(image) or "Erreur : stop")
    run_code(app, language="python", code="print(1)")
    assert seen == ["python:3.12-slim"]

def test_the_container_is_cut_off_from_everything():
    command: str = " ".join(sandbox("n", "img", ["cmd"], "256m"))
    for flag in ("--network none", "--read-only", "--cap-drop ALL", "--security-opt no-new-privileges",
                 "--pids-limit 64", "--memory 256m", "--memory-swap 256m", "--user 65534:65534", "--pull never"):
        assert flag in command
    # Nothing of the project, or of the machine, is mounted
    assert "--volume" not in command and " -v " not in command and "--mount" not in command
    assert command.endswith("img cmd")

def test_capture_keeps_the_start_and_counts_the_rest():
    class Stream:
        def __init__(self): self.chunks = [b"abcdef", b"ghij", b""]
        def read1(self, size): return self.chunks.pop(0)
    capture = Capture(Stream(), 8)
    capture.run()
    assert (capture.text, capture.total) == ("abcdefgh", 10)

@needs_python
def test_the_output_comes_back(app):
    result = run_code(app, language="python", code="print(6 * 7)\n")
    assert result == "Code de sortie : 0\n--- stdout ---\n42"

@needs_python
def test_an_error_of_the_program_is_its_output_not_one_of_the_tool(app):
    result = run_code(app, language="python", code="1 / 0\n")
    assert result.startswith("Code de sortie : 1") and "ZeroDivisionError" in result

@needs_python
def test_the_code_has_no_network(app):
    code = "import socket\ntry:\n    socket.create_connection(('1.1.1.1', 80), timeout=2)\nexcept OSError as e:\n    print('blocked')\n"
    assert "blocked" in run_code(app, language="python", code=code)

@needs_python
def test_the_code_can_not_write_outside_tmp(app):
    code = "open('/tmp/ok', 'w').write('x')\nprint('tmp ok')\nopen('/etc/x', 'w')\n"
    result = run_code(app, language="python", code=code)
    assert "tmp ok" in result and "Read-only file system" in result

@needs_python
def test_the_project_is_not_there(app, folder):
    (folder / "secret.txt").write_text("hunter2")
    code = f"import os\nprint(os.path.exists({str(folder / 'secret.txt')!r}))\n"
    assert run_code(app, language="python", code=code).endswith("False")

@needs_python
def test_a_program_that_never_ends_is_stopped_with_what_it_printed(app):
    app.settings["sandbox.timeout"] = 2
    result = run_code(app, language="python", code="import time\nprint('start')\ntime.sleep(60)\n")
    assert result.startswith("Erreur : le code n'a pas fini en 2s") and "start" in result
    # The container is stopped, not only the docker command that watched it
    assert tool_run.run("ps", "--filter", "name=louis-sandbox", "--format", "{{.Names}}") == (True, "")

@needs_python
def test_a_program_that_prints_without_end_is_cut(app):
    app.settings["sandbox.timeout"] = 3
    result = run_code(app, language="python", code="while True:\n    print('x' * 1000)\n")
    assert len(result) < 3 * tool_run.OUTPUT and "coupés" in result

@needs_python
def test_the_processes_it_can_start_are_limited(app):
    code = ("import subprocess\nn = 0\nfor _ in range(200):\n    try:\n        subprocess.Popen(['sleep', '5'])\n"
            "        n += 1\n    except OSError:\n        break\nprint(n)\n")
    started = int(run_code(app, language="python", code=code).splitlines()[-1])
    assert 0 < started < 64

@needs_python
def test_the_memory_limit_kills_a_program_that_eats_it(app):
    result = run_code(app, language="python", code="x = bytearray(1024 ** 3)\nprint(len(x))\n")
    assert result.startswith("Code de sortie : 137")

@needs_sh
def test_a_shell_script_runs_too(app):
    assert run_code(app, language="sh", code="echo hello; id -u").endswith("hello\n65534")
