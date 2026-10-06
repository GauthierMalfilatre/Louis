##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Embedder: the meaning of a text as a vector, by an embedding model of Ollama
##
import requests
from logger.logger import log

class EmbedError(Exception):
    """ The embedding model did not answer: Ollama is stopped, or the model is not downloaded """
    def __init__(self, message: str):
        super().__init__(message)
        self.message: str = message

class Embedder:
    """ Embedder Class, to embed texts with the API of Ollama """
    def __init__(self, uri: str, model: str, query_prefix: str = "", document_prefix: str = "", batch: int = 32):
        """
            Init the embedder. The prefixes tell the model which side of the search a text is: nomic-embed-text
            wants "search_query: " and "search_document: ", other models none. batch is the texts sent at once
        """
        self.__uri            : str = uri
        self.__model          : str = model
        self.__query_prefix   : str = query_prefix
        self.__document_prefix: str = document_prefix
        self.__batch          : int = max(1, batch)

    @property
    def model(self) -> str:
        """ Get the name of the embedding model """
        return self.__model

    def documents(self, texts: list[str]) -> list[list[float]]:
        """ The vectors of passages to search in, in the same order. NOTE: Raisable (EmbedError) """
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.__batch):
            vectors.extend(self.__embed([self.__document_prefix + text for text in texts[i:i + self.__batch]]))
        return vectors

    def query(self, text: str) -> list[float]:
        """ The vector of a question. NOTE: Raisable (EmbedError) """
        return self.__embed([self.__query_prefix + text])[0]

    def __embed(self, texts: list[str]) -> list[list[float]]:
        """ Ask Ollama for the vectors of these texts """
        try:
            res = requests.post(
                f"{self.__uri}/api/embed",
                # A text longer than the model reads is cut by Ollama, not refused
                json={"model": self.__model, "input": texts, "truncate": True},
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
