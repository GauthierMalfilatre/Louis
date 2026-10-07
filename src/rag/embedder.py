##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Embedder: the meaning of a text as a vector, by an embedding model of Ollama
##
import requests
from logger.logger import log

# All the layers of the model on the GPU: more than any embedding model has, Ollama keeps to what there is
GPU_LAYERS: int = 999

class EmbedError(Exception):
    """ The embedding model did not answer: Ollama is stopped, or the model is not downloaded """
    def __init__(self, message: str):
        super().__init__(message)
        self.message: str = message

class Embedder:
    """ Embedder Class, to embed texts with the API of Ollama """
    def __init__(self, uri: str, model: str, query_prefix: str = "", document_prefix: str = "", batch: int = 32,
                 gpu: bool = False):
        """
            Init the embedder. The prefixes tell the model which side of the search a text is: nomic-embed-text
            wants "search_query: " and "search_document: ", other models none. batch is the texts sent at once.
            Without gpu, the questions are embedded on the CPU: one takes ~30 ms, and on a GPU of a few GB each MB the
            model leaves goes to the chat model, which writes faster the more of it is on the GPU. The passages of an
            indexing always go to the GPU: hundreds of them at once, ~50 times faster there (Ollama moves the model
            once, when it goes from the one to the other)
        """
        self.__uri            : str  = uri
        self.__model          : str  = model
        self.__query_prefix   : str  = query_prefix
        self.__document_prefix: str  = document_prefix
        self.__batch          : int  = max(1, batch)
        self.__gpu            : bool = gpu

    @property
    def model(self) -> str:
        """ Get the name of the embedding model """
        return self.__model

    def documents(self, texts: list[str], gpu: bool = True) -> list[list[float]]:
        """
            The vectors of passages to search in, in the same order: on the GPU, unless a few texts at a time are not
            worth moving the model there (the description of a session). NOTE: Raisable (EmbedError)
        """
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.__batch):
            vectors.extend(self.__embed([self.__document_prefix + text for text in texts[i:i + self.__batch]], gpu))
        return vectors

    def query(self, text: str) -> list[float]:
        """ The vector of a question. NOTE: Raisable (EmbedError) """
        return self.__embed([self.__query_prefix + text], self.__gpu)[0]

    def __embed(self, texts: list[str], gpu: bool) -> list[list[float]]:
        """ Ask Ollama for the vectors of these texts, on the GPU or on the CPU """
        try:
            res = requests.post(
                f"{self.__uri}/api/embed",
                # A text longer than the model reads is cut by Ollama, not refused. num_gpu: the layers on the GPU, said
                # each time (0: none, 999: all of them, Ollama keeps to what there is), or Ollama keeps the model where
                # the last request put it
                json={"model": self.__model, "input": texts, "truncate": True, "options": {"num_gpu": GPU_LAYERS if gpu else 0}},
                timeout=(5.0, 120.0)
            )
        except requests.RequestException as e:
            raise EmbedError(f"Ollama ne répond pas à {self.__uri} ({type(e).__name__})") from e
        if res.status_code == 404:
            raise EmbedError(f"Le modèle d'embedding {self.__model} n'est pas téléchargé : ollama pull {self.__model}")
        if res.status_code != 200:
            raise EmbedError(f"Ollama a refusé l'embedding avec {self.__model} ({res.status_code})")
        vectors: list[list[float]] = res.json().get("embeddings") or []
        if len(vectors) != len(texts):
            log.warning(f"[rag] {len(texts)} texts sent to {self.__model}, {len(vectors)} vectors back")
            raise EmbedError(f"Le modèle {self.__model} n'a pas renvoyé un vecteur par texte")
        return vectors
