##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Reranker: the passages found, read again with the question by a cross-encoder, and scored on how well they answer
##
## The search (rag/index.py) embeds the question and the passages apart, and its fusion (RRF) only gives a rank:
## it finds what may answer. A cross-encoder reads the question and one passage together and gives a score of how
## well the passage answers it: it puts the right passage first, and its score can be compared to a threshold, below
## which a passage is a near-miss left out of the context. It reads every pair, so it only reads the few passages
## the search found. ONNX on the CPU, by fastembed (no torch): the GPU is the chat model's.
## Download the model once:  cd src && python -m rag.reranker
##
from logger.logger import log
import math
import os
import sys
import time

# Where the models are kept: fastembed's default is in /tmp, emptied when the machine restarts
CACHE: str = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "louis", "rerank")

# Cross-encoders fastembed does not list, registered before loading: their Hugging Face repository and its ONNX file
EXTRA_MODELS: dict[str, tuple[str, str]] = {
    # Multilingual (trained on mMARCO, French among its languages), Apache-2.0. Most of its weights are its vocabulary,
    # that costs memory, not time: its layers are a MiniLM, several times lighter to run than jina-reranker-v2
    "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1": ("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1", "onnx/model.onnx"),
    # The same, its weights in 8 bits for the processors with AVX2 (most of those since 2013): faster, a little less exact
    "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1-avx2": ("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
                                                        "onnx/model_quint8_avx2.onnx"),
}

class RerankError(Exception):
    """ The reranker cannot score: fastembed is not installed, or the model is not downloaded """
    def __init__(self, message: str):
        super().__init__(message)
        self.message: str = message

class Reranker:
    """ Reranker Class, to score passages against a question with a cross-encoder of fastembed """
    def __init__(self, model: str, pool: int = 20, min_score: float = 0.0, max_chars: int = 0, cache: str = CACHE,
                 threads: int | None = None):
        """
            Init the reranker: the model is loaded on the first score, from the cache only (never downloaded then).
            pool is the passages of the search it reads, min_score the score under which a passage is left out, max_chars
            what it reads of each one (0: all it can). Its time grows with what it reads: on a CPU, about half as
            long for a passage cut to 600 characters as for a whole one of 1500
        """
        self.__model    : str          = model
        self.__pool     : int          = max(1, pool)
        self.__min_score: float        = min_score
        self.__max_chars: int          = max(0, max_chars)
        self.__cache    : str          = cache
        self.__threads  : int | None   = threads
        self.__encoder                 = None
        # Why it could not load: it is not tried again on every search, each try costs seconds
        self.__broken   : str | None   = None

    @property
    def model(self) -> str:
        """ Get the name of the model """
        return self.__model

    @property
    def pool(self) -> int:
        """ Get how many passages of the search it reads """
        return self.__pool

    @property
    def min_score(self) -> float:
        """ Get the score under which a passage is left out """
        return self.__min_score

    def score(self, query: str, texts: list[str]) -> list[float]:
        """ How well each text answers the query, from 0 to 1, in the same order. NOTE: Raisable (RerankError) """
        if not texts:
            return []
        encoder = self.__load()
        if self.__max_chars:
            texts = [text[:self.__max_chars] for text in texts]
        try:
            logits: list[float] = list(encoder.rerank(query, texts))
        except Exception as e:
            raise RerankError(f"Le reranker {self.__model} a échoué ({type(e).__name__} : {e})") from e
        # The model gives logits: the sigmoid puts them between 0 and 1 (the order stays), a threshold reads better there
        return [1 / (1 + math.exp(-logit)) if logit > -700 else 0.0 for logit in logits]

    def download(self) -> None:
        """ Download the model to the cache, if it is not there. NOTE: Raisable (RerankError) """
        self.__load(local_only=False)

    def __load(self, local_only: bool = True):
        """ The cross-encoder, loaded once """
        if self.__encoder is not None:
            return self.__encoder
        if self.__broken is not None and local_only:
            raise RerankError(self.__broken)
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
            from fastembed.common.model_description import ModelSource
        except ImportError as e:
            self.__broken = f"le reranking a besoin de fastembed : pip install -r requirements-rerank.txt ({e})"
            raise RerankError(self.__broken) from e
        try:
            # fastembed writes its errors to the terminal (loguru): over the curses window of Louis. Ours go to the log
            from loguru import logger
            logger.disable("fastembed")
        except ImportError:
            pass
        known: set[str] = {description["model"] for description in TextCrossEncoder.list_supported_models()}
        if self.__model in EXTRA_MODELS and self.__model not in known:
            repository, file = EXTRA_MODELS[self.__model]
            TextCrossEncoder.add_custom_model(self.__model, ModelSource(hf=repository), file)
        start: float = time.perf_counter()
        try:
            self.__encoder = TextCrossEncoder(
                model_name=self.__model, cache_dir=self.__cache, threads=self.__threads, cuda=False,
                local_files_only=local_only
            )
        except Exception as e:
            self.__broken = (f"le modèle de reranking {self.__model} n'est pas téléchargé : cd src && python -m rag.reranker"
                             if local_only else f"le modèle {self.__model} n'a pas pu être téléchargé ({type(e).__name__} : {e})")
            raise RerankError(self.__broken) from e
        self.__broken = None
        log.info(f"[rag] reranker {self.__model} loaded in {time.perf_counter() - start:.1f}s")
        return self.__encoder

if __name__ == "__main__":
    from config.settings import settings
    model: str = sys.argv[1] if len(sys.argv) > 1 else settings.get("rag.rerank.model", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
    print(f"Téléchargement de {model} dans {CACHE}...")
    try:
        Reranker(model).download()
    except RerankError as e:
        sys.stderr.write(f"{e.message}\n")
        sys.exit(1)
    print("Prêt.")
