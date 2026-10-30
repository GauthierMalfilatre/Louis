##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Policy checks: the model reads a message against a policy of prompts.yml and answers Yes (block) or No (pass)
##
## They replace the built-in self check input / output of NeMo, which ask Ollama through its OpenAI API (/v1): it can
## not set num_ctx nor keep_alive (Ollama 0.34 ignores them there), so Ollama loaded the model with its own context
## for every check, and loaded it again with Louis' for the next request of the chat: 12 to 18 s twice per check with
## qwen3.5:9b on a laptop. Here the native API is asked with the context and the keep-alive of the chat: the model
## Ollama has loaded is the one asked for, and nothing is reloaded. NeMo still runs the flows and every other rail,
## and never calls a model any more.
## Plain Python, without NeMo: config/actions.py only hands NeMo what it needs from here
##
from dataclasses import dataclass
from logger.logger import log
import re
import requests

ALLOWED: str = "allowed"
BLOCKED: str = "blocked"
# The model could not be asked: the message is refused (never let through unchecked), with its own refusal
ERROR  : str = "error"

# What the model writes at most: a Yes or a No, and a few words if it adds some
PREDICT: int = 16

class PolicyError(Exception):
    """ The model did not answer: message says why """
    def __init__(self, message: str):
        super().__init__(message)
        self.message: str = message

@dataclass(frozen=True, slots=True)
class Judge:
    """ The model that reads the messages, as Louis loads it: the same context and keep-alive as the chat """
    uri      : str
    model    : str
    context  : int
    keepalive: str   = "30m"
    timeout  : float = 120.0

    @classmethod
    def from_settings(cls, settings: dict) -> "Judge":
        """
            The judge of the settings: guard.model, or the chat model with the context of the chat (another context
            would make Ollama reload it, which this module is here to avoid)
        """
        chat: str = f"{settings['chat.model.name']}:{settings['chat.model.parameters']}"
        model: str = settings.get("guard.model") or chat
        context: int = settings.get("chat.context", 12288) if model == chat else settings.get("guard.context", 4096)
        return cls(settings.get("chat.uri", "http://localhost:11434"), model, context,
                   settings.get("chat.keepalive", "30m"), settings.get("guard.timeout", 120.0))

    def as_dict(self) -> dict:
        """ The judge as NeMo carries it to the actions (custom_data) """
        return {"uri": self.uri, "model": self.model, "context": self.context, "keepalive": self.keepalive,
                "timeout": self.timeout}

def render(template: str, **values: str) -> str:
    """
        A prompt of prompts.yml, its {{ name }} replaced by the values. Only the plain variables NeMo's Jinja would
        fill: the prompts of Louis use no filter nor block, and a value is put in as it is, never read as a template
    """
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda match: values.get(match[1], match[0]), template)

def allowed(answer: str) -> bool:
    """
        Whether the answer of the model lets the message through, read as NeMo 0.24 reads it (is_content_safe): only
        its first two words count, "yes" or "unsafe" block, "no" or "safe" pass, in that order of looking. Anything
        else blocks: a check that did not say No is not a pass
    """
    words: list[str] = re.sub(r"\W+", " ", answer.lower().strip()).split(" ")[:2]
    for word, verdict in (("safe", True), ("unsafe", False), ("yes", False), ("no", True)):
        if word in words:
            return verdict
    return False

def ask(judge: Judge, prompt: str) -> str:
    """ The answer of the model to a filled prompt, by the native API of Ollama. NOTE: Raisable (PolicyError) """
    try:
        res = requests.post(f"{judge.uri}/api/chat", timeout=(5.0, judge.timeout), json={
            "model": judge.model,
            # As NeMo sent it: the whole prompt in one message
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            # A check answers at once: thinking first, qwen3 takes ~30s instead of ~4s
            "think": False,
            "keep_alive": judge.keepalive,
            "options": {"num_ctx": judge.context, "num_predict": PREDICT, "temperature": 0}
        })
    except requests.RequestException as e:
        raise PolicyError(f"Ollama ne répond pas à {judge.uri} ({type(e).__name__})") from e
    if res.status_code == 404:
        raise PolicyError(f"Le modèle {judge.model} n'est pas téléchargé : ollama pull {judge.model}")
    if res.status_code != 200:
        raise PolicyError(f"Ollama a refusé la vérification ({res.status_code} : {res.text[:200]})")
    try:
        return (res.json().get("message") or {}).get("content") or ""
    except ValueError as e:
        raise PolicyError(f"Réponse illisible d'Ollama ({e})") from e

def check(judge: Judge, template: str, **values: str) -> str:
    """ ALLOWED, BLOCKED, or ERROR when the model could not be asked: never raises """
    try:
        answer: str = ask(judge, render(template, **values))
    except PolicyError as e:
        log.warning(f"[guard] the policy check could not be made: {e.message}")
        return ERROR
    verdict: str = ALLOWED if allowed(answer) else BLOCKED
    log.debug(f"[guard] policy check: {verdict} ({answer.strip()[:80]!r})")
    return verdict
