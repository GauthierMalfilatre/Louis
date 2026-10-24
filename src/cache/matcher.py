##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Matcher of the semantic cache: a small model of Ollama tells whether two questions are the same one
##
## The reranker was trained to find the passages that answer a question, not to tell two questions apart: it confirms
## 4 paraphrases out of 27 (python -m cache.evaluate), "tu peux me redire comment fonctionne X" against "comment marche
## X" gets 0.010. A small model asked the question itself confirms 20 of them, and none of the 26 that ask something
## else ("lire" and "écrire un fichier JSON", "comment marche X" and "comment modifier X"). It is the last word on the
## questions close in meaning that the reranker did not confirm: ~2.4 s on the CPU (qwen3:4b-instruct, the model of the
## scribe), against a whole turn of the chat model and the guard
##
## Usage:  matcher = Matcher(uri, "qwen3:4b-instruct")
##         matcher.same("Comment marche X ?", "Tu peux me redire comment fonctionne X ?")   -> True
##
import json
import requests

PROMPT: str = (
    "Deux questions posées à un assistant de programmation. Réponds same: true seulement si une seule et même réponse "
    "répond exactement aux deux : même demande, même action (lire ≠ écrire, créer ≠ supprimer, marcher ≠ modifier), "
    "mêmes objets, mêmes détails. Une formulation différente ne compte pas. Sinon same: false."
)
SCHEMA: dict = {"type": "object", "properties": {"same": {"type": "boolean"}}, "required": ["same"]}
# All the layers of the model on the GPU, or none: Ollama keeps to what there is
GPU_LAYERS: int = 999

class MatchError(Exception):
    """ The model did not answer: Ollama is stopped, the model is not downloaded, or its answer is no verdict """
    def __init__(self, message: str):
        super().__init__(message)
        self.message: str = message

class Matcher:
    """ Matcher Class: asks a small model of Ollama whether two questions are the same, as JSON """
    def __init__(self, uri: str, model: str, gpu: bool = False, keepalive: str = "30m", timeout: float = 60.0):
        """
            Init the matcher on a model of Ollama: an "instruct" one, it must answer without thinking first. On the CPU
            unless gpu: the GPU stays the chat model's, which writes faster the more of it is there
        """
        self.__uri      : str   = uri
        self.__model    : str   = model
        self.__gpu      : bool  = gpu
        self.__keepalive: str   = keepalive
        self.__timeout  : float = timeout

    @property
    def model(self) -> str:
        """ Get the name of the model """
        return self.__model

    def same(self, first: str, second: str) -> bool:
        """ Whether one and the same answer answers both questions. NOTE: Raisable (MatchError) """
        try:
            res = requests.post(f"{self.__uri}/api/chat", json={
                "model": self.__model, "stream": False, "format": SCHEMA, "keep_alive": self.__keepalive,
                "options": {"temperature": 0, "num_gpu": GPU_LAYERS if self.__gpu else 0, "num_ctx": 1024,
                            "num_predict": 20},
                "messages": [{"role": "system", "content": PROMPT},
                             {"role": "user", "content": f"Question 1 : {first}\nQuestion 2 : {second}"}]
            }, timeout=(5.0, self.__timeout))
        except requests.RequestException as e:
            raise MatchError(f"Ollama ne répond pas à {self.__uri} ({type(e).__name__})") from e
        if res.status_code == 404:
            raise MatchError(f"Le modèle {self.__model} n'est pas téléchargé : ollama pull {self.__model}")
        if res.status_code != 200:
            raise MatchError(f"Ollama a refusé la comparaison avec {self.__model} ({res.status_code})")
        try:
            verdict = json.loads(res.json()["message"]["content"])["same"]
        except (ValueError, KeyError, TypeError) as e:
            raise MatchError(f"Le modèle {self.__model} n'a pas donné de verdict ({type(e).__name__})") from e
        return verdict is True
