##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Describer: what a passage of code does, in one sentence of plain words, written by the chat model at indexing
##
## Code says what it does with identifiers (pygame.K_LEFT, fuel, except KeyboardInterrupt), questions with words
## ("the keyboard keys", "le carburant", "Ctrl+C"): neither the embeddings, nor the keywords, nor the reranker link
## them. A sentence written by the model for each passage holds the words a question uses ("lit les flèches du
## clavier et les convertit en actions des moteurs"): it is searched with the passage, the model of the chat reads
## the code itself. One request per passage: a source asks for it (/index --describe), its code files only.
##
## Its time is what the model writes: the answer is kept short (one sentence and a few keywords). The requests of a
## file share the start of their prompt (the instructions, the file, its outline): Ollama reads it once
##
import re
import requests
from logger.logger import log

# The instructions, the same for every request: the start of the prompt Ollama keeps from one request to the next.
# They do not say what the sentence is for: the model then writes it in its answer ("pour un moteur de recherche")
INSTRUCTIONS: str = (
    "Tu lis un passage d'un fichier de code et tu dis ce qu'il fait. Réponds par une seule phrase en français, avec "
    "les mots simples de quelqu'un qui décrirait ce comportement sans connaître le code (« lit les touches du "
    "clavier », « sauvegarde le modèle »), puis « Mots-clés : » et cinq mots-clés en anglais. Ne recopie pas le "
    "code, ne commence pas par « Ce passage ». Rien d'autre."
)
# What is kept of an answer: one sentence and its keywords, never a page
MOST_CHARS: int = 400

class DescribeError(Exception):
    """ The chat model did not answer: Ollama is stopped, or the model is not downloaded """
    def __init__(self, message: str):
        super().__init__(message)
        self.message: str = message

class Describer:
    """ Describer Class, to describe passages of code with the chat model of Ollama """
    def __init__(self, uri: str, model: str, context: int, keepalive: str = "30m", predict: int = 80,
                 timeout: float = 300.0):
        """
            Init the describer. context is the num_ctx of the chat (the same, or Ollama reloads the model between
            the chat and the indexing), predict the tokens an answer may take: its time is mostly them
        """
        self.__uri      : str   = uri
        self.__model    : str   = model
        self.__context  : int   = context
        self.__keepalive: str   = keepalive
        self.__predict  : int   = predict
        self.__timeout  : float = timeout

    @property
    def model(self) -> str:
        """ Get the name of the model that writes the descriptions """
        return self.__model

    def describe(self, path: str, outline: str, lines: tuple[int, int], context: str, text: str) -> str:
        """
            What a passage does, in one sentence and some keywords. The prompt starts with what the passages of a file
            share (the file, its outline), the passage comes last. NOTE: Raisable (DescribeError)
        """
        where: str = f", {context}" if context else ""
        prompt: str = (f"Fichier : {path}\nPlan du fichier :\n{outline or '(aucun)'}\n\n"
                       f"Passage, lignes {lines[0]}-{lines[1]}{where} :\n```\n{text}\n```")
        try:
            res = requests.post(f"{self.__uri}/api/chat", timeout=(5.0, self.__timeout), json={
                "model": self.__model,
                "stream": False,
                "think": False,
                "keep_alive": self.__keepalive,
                "options": {"num_ctx": self.__context, "num_predict": self.__predict, "temperature": 0},
                "messages": [{"role": "system", "content": INSTRUCTIONS}, {"role": "user", "content": prompt}]
            })
        except requests.RequestException as e:
            raise DescribeError(f"Ollama ne répond pas à {self.__uri} ({type(e).__name__})") from e
        if res.status_code == 404:
            raise DescribeError(f"Le modèle {self.__model} n'est pas téléchargé : ollama pull {self.__model}")
        if res.status_code != 200:
            raise DescribeError(f"Ollama a refusé la description avec {self.__model} ({res.status_code})")
        answer: str = ((res.json().get("message") or {}).get("content") or "")
        description: str = clean(answer)
        if not description:
            log.warning(f"[rag] {self.__model} gave no description for {path}:{lines[0]}-{lines[1]}")
        return description

def clean(answer: str) -> str:
    """ An answer on one line: without the markup the model adds (**, `), its thinking if any, cut to MOST_CHARS """
    answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL)
    answer = re.sub(r"[*`#]+", "", answer)
    answer = " ".join(answer.split())
    return answer if len(answer) <= MOST_CHARS else answer[:MOST_CHARS - 1] + "…"
