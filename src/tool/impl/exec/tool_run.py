##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Run tool: run a piece of code in a container with no network, no project and no way out
##
from tool.tool import Tool
import shutil
import subprocess
import threading
import uuid

# What runs the code of each language: its image (settings "sandbox.images" may name another) and its command, which
# reads the code on stdin: no file is written, no folder of the project is mounted
LANGUAGES: dict[str, tuple[str, list[str]]] = {
    "python": ("python:3.13-alpine", ["python3", "-u", "-"]),
    "sh": ("alpine:latest", ["sh", "-s"]),
}
# The names small models give a language instead of the ones of the tool: the language they mean
ALIASES: dict[str, str] = {
    "py": "python", "python3": "python", "bash": "sh", "shell": "sh", "zsh": "sh",
}

TIMEOUT = 10
MEMORY = "256m"
OUTPUT = 4000
# The code goes through a pipe the container reads as it runs: kept below the 64 KiB of a pipe, writing it never blocks
MAX_CODE = 30000

def available() -> bool:
    """ Whether the docker command is installed: without it the tool is not offered to the model """
    return shutil.which("docker") is not None

def run(*args: str, timeout: int = 15) -> tuple[bool, str]:
    """ Run docker without a shell, and say if it worked: what the model writes is never read by bash """
    try:
        res = subprocess.run(["docker", *args], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                             errors="replace", timeout=timeout)
    except FileNotFoundError:
        return False, "docker n'est pas installé."
    except subprocess.TimeoutExpired:
        return False, f"docker n'a pas répondu en {timeout}s."
    return res.returncode == 0, (res.stdout + res.stderr).strip()

class Capture(threading.Thread):
    """
        Read a stream to its end, and keep its first bytes only: a program that prints without end is read at the speed
        it prints, but never fills the memory of Louis. total is what it printed, kept or not
    """
    def __init__(self, stream, limit: int):
        super().__init__(daemon=True)
        self.__stream = stream
        self.__limit: int = limit
        self.__kept: bytearray = bytearray()
        self.total: int = 0

    def run(self) -> None:
        """ Read until the stream is closed, by the end of the program or by its kill """
        while chunk := self.__stream.read1(65536):
            self.total += len(chunk)
            self.__kept += chunk[:max(0, self.__limit - len(self.__kept))]

    @property
    def text(self) -> str:
        """ What was kept, as text: a cut inside a character, or a program that prints bytes, is not an error """
        return self.__kept.decode("utf-8", errors="replace")

def sandbox(name: str, image: str, command: list[str], memory: str) -> list[str]:
    """
        The docker command that runs a program cut off from everything: no network, a read-only disk but a small
        /tmp, nobody as the user, no capability and no way to get one, and limits on processes, memory and cpu
    """
    return [
        "docker", "run", "--rm", "--init", "--interactive", "--name", name, "--pull", "never",
        "--network", "none", "--read-only", "--tmpfs", "/tmp:size=16m,noexec", "--workdir", "/tmp",
        "--user", "65534:65534", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "64", "--memory", memory, "--memory-swap", memory, "--cpus", "1",
        "--env", "HOME=/tmp", "--env", "PYTHONDONTWRITEBYTECODE=1",
        image, *command,
    ]

def image_problem(image: str) -> str | None:
    """ Why the image can not run, or None if it can: no docker daemon, or an image the user has not pulled """
    ok, out = run("image", "inspect", "--format", "{{.Id}}", image)
    if ok:
        return None
    if "No such image" in out:
        return f"Erreur : l'image {image} n'est pas installée. L'utilisateur doit lancer : docker pull {image}"
    return f"Erreur : docker ne répond pas : {out}"

def shown(label: str, text: str, total: int, limit: int) -> str:
    """ A stream of the program under its label, with what was cut if it printed more than the limit """
    if total == 0:
        return ""
    cut = f"\n[... {total - limit} octets de plus, coupés]" if total > limit else ""
    return f"--- {label} ---\n{text.rstrip()}{cut}\n"

class RunTool(Tool):
    def __init__(self):
        super().__init__(
            "run_code",
            "Exécute du code et renvoie sa sortie, pour tester une idée, un calcul ou un script avant de l'écrire "
            "dans un fichier. Le code tourne dans un conteneur isolé : sans réseau, sans accès aux fichiers du projet, "
            "et arrêté au bout de quelques secondes. Il ne peut donc ni installer de paquet, ni lire ou modifier le "
            "projet : pour ça, utilise cat_file et edit_file. Affiche ce que tu veux voir (print, echo) : "
            "seule la sortie te revient.",
            {
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        "enum": list(LANGUAGES)
                    },
                    "code": {
                        "type": "string",
                        "description": "Le programme complet à exécuter, qui affiche son résultat"
                    }
                },
                "required": ["language", "code"]
            }
        )

    def handle(self, app, **kwargs) -> str:
        """ Run the code in the sandbox, after the user has read it """
        extra: list[str] = [name for name in kwargs if name not in ("language", "code")]
        if extra:
            return f"Erreur : {', '.join(extra)} n'existe pas pour {self.name}. Ses paramètres sont : language, code."
        language, code = kwargs.get("language"), kwargs.get("code")
        if not isinstance(language, str) or not isinstance(code, str) or not code.strip():
            return "Erreur : 'language' et 'code' sont requis, et doivent être du texte."
        language = ALIASES.get(language.strip().lower(), language.strip().lower())
        if language not in LANGUAGES:
            return f"Erreur : le langage '{language}' n'est pas disponible. Les langages sont : {', '.join(LANGUAGES)}."
        if len(code.encode("utf-8")) > MAX_CODE:
            return f"Erreur : ce code est trop long pour {self.name} ({MAX_CODE} octets au plus) : écris-le dans un fichier."

        settings: dict = getattr(app, "settings", None) or {}
        image: str = {**{k: v[0] for k, v in LANGUAGES.items()}, **settings.get("sandbox.images", {})}[language]
        # Before asking the user: no point in letting them read code that can not run
        if (problem := image_problem(image)) is not None:
            return problem
        if not app.permissions.request(self.name, f"Exécution de code {language} dans un conteneur isolé", code):
            return ("Refusé : l'utilisateur n'a pas autorisé l'exécution. "
                    "Ne la retente pas : demande-lui ce qu'il veut à la place.")
        return self.__execute(language, image, code, int(settings.get("sandbox.timeout", TIMEOUT)),
                              str(settings.get("sandbox.memory", MEMORY)), int(settings.get("sandbox.output", OUTPUT)))

    def __execute(self, language: str, image: str, code: str, timeout: int, memory: str, limit: int) -> str:
        """ Start the container, hand it the code, and give back what it printed, or why it was stopped """
        name: str = f"louis-sandbox-{uuid.uuid4().hex[:12]}"
        try:
            proc = subprocess.Popen(sandbox(name, image, LANGUAGES[language][1], memory),
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as e:
            return f"Erreur : docker n'a pas pu démarrer : {e.strerror or e}"
        out, err = Capture(proc.stdout, limit), Capture(proc.stderr, limit)
        out.start()
        err.start()
        try:
            proc.stdin.write(code.encode("utf-8"))
            proc.stdin.close()
        except BrokenPipeError:
            # The program ended before reading its code: its exit code tells why
            pass

        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            # Killing the docker command leaves the container running: it is stopped by its name
            run("kill", name)
            proc.kill()
            proc.wait()
        # The streams end with the program: a reader that does not is a daemon, and is left behind
        out.join(2)
        err.join(2)

        stdout, stderr = shown("stdout", out.text, out.total, limit), shown("stderr", err.text, err.total, limit)
        if timed_out:
            return f"Erreur : le code n'a pas fini en {timeout}s, il a été arrêté.\n{stdout}{stderr}".rstrip()
        # 125 is docker itself failing (no daemon...), whatever the program would have returned
        if proc.returncode == 125 and err.text.lstrip().startswith("docker:"):
            return f"Erreur : docker n'a pas pu lancer le conteneur : {err.text.strip()}"
        status = f"Code de sortie : {proc.returncode}"
        if proc.returncode == 137:
            status += " (tué, sans doute par la limite de mémoire de " + memory + ")"
        return f"{status}\n{stdout}{stderr}".rstrip() if (stdout or stderr) else f"{status}\n(aucune sortie)"
