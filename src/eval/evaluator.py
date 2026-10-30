##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Evaluator: every answer of Louis judged once its turn is done, the scores told on the bus (EVAL_SCORED)
##
## In the background (eval.background), a thread judges the answers one after the other, and the user never waits
## for it. It only asks the model while Louis is not answering: Ollama then gives the chat its whole GPU (a request of
## the judge already sent goes on, the next one waits for the end of the turn). The judgments of the background are
## told only to the monitoring and the log: written into the conversation, they would cut a reply being streamed or a
## line being typed. /eval shows the last one, from the thread of the app.
## Without the background (eval.bench), the answer is judged as soon as its turn ends
##
from eval.collector import Collector
from eval.judge import Judge, Judgment
from eval.sample import Sample
from events.event import Event
from events.event_bus import EventBus
from events.event_list import CHAT_TURN_STARTED, CHAT_TURN_ENDED, EVAL_STARTED, EVAL_SCORED
from logger.logger import log
import queue
import random
import threading

# Answers waiting for the judge at most: past them, the new ones are left out (/eval still judges the last one)
MAX_PENDING: int = 4

class Job:
    """ An answer to judge, and its judgment once done """
    def __init__(self, sample: Sample, queued: bool):
        self.sample  : Sample            = sample
        # Given to the judge by itself: judged in the background, or only if /eval asks
        self.queued  : bool              = queued
        self.judgment: Judgment | None   = None
        self.done    : threading.Event   = threading.Event()

class Evaluator:
    """ Judges the answers the collector gives, and keeps the last one for /eval """
    def __init__(self, settings: dict, bus: EventBus, judge: Judge | None = None):
        """ Init the evaluator on the bus of the app: it collects from now on, and judges as eval.* says """
        self.__bus       : EventBus = bus
        self.__enabled   : bool     = bool(settings.get("eval.enabled", True))
        self.__background: bool     = bool(settings.get("eval.background", True))
        self.__rate      : float    = float(settings.get("eval.sample", 1.0))
        # Set while Louis is not answering: the judge of the background asks the model only then
        self.__idle      : threading.Event = threading.Event()
        self.__idle.set()
        self.__judge     : Judge = judge or Judge.from_settings(settings, before=self.__idle.wait)
        self.__last      : Job | None = None
        self.__lock      : threading.Lock = threading.Lock()
        self.__queue     : queue.Queue[Job] = queue.Queue(maxsize=MAX_PENDING)

        bus.subscribe(lambda event: self.__idle.clear(), CHAT_TURN_STARTED)
        # Before the collector: the sample of the turn is judged once Louis is idle again
        bus.subscribe(lambda event: self.__idle.set(), CHAT_TURN_ENDED)
        Collector(self.__on_sample, settings.get("eval.sources") or []).bind(bus)
        if self.__enabled and self.__background:
            threading.Thread(target=self.__work, daemon=True, name="louis-eval").start()
        log.info(f"[eval] judge: {self.__judge.model}, "
                 f"{'every answer' if self.__enabled else 'on /eval only'}{' in the background' if self.__background else ''}")

    @property
    def judge(self) -> Judge:
        """ Get the judge """
        return self.__judge

    def last(self) -> Judgment | None:
        """
            The judgment of the last answer, None if there is none: waited for when the background is on it, judged
            now when nobody was going to (eval.enabled off, left out by eval.sample or a queue full)
        """
        with self.__lock:
            job: Job | None = self.__last
        if job is None:
            return None
        if not job.queued and not job.done.is_set():
            self.__run(job)
        job.done.wait()
        return job.judgment

    def __on_sample(self, sample: Sample) -> None:
        """ An answer done: judged now, given to the background, or kept for /eval """
        judged: bool = self.__enabled and random.random() < self.__rate
        job: Job = Job(sample, judged)
        with self.__lock:
            self.__last = job
        if not judged:
            return
        if not self.__background:
            self.__run(job)
            return
        try:
            self.__queue.put_nowait(job)
        except queue.Full:
            job.queued = False
            log.warning(f"[eval] {MAX_PENDING} answers already wait for the judge: {sample.id} left out")

    def __work(self) -> None:
        """ The thread of the background: the answers one after the other, as long as Louis runs """
        while True:
            job: Job = self.__queue.get()
            # /eval may have judged it already, from the thread of the app
            if not job.done.is_set():
                self.__run(job)

    def __run(self, job: Job) -> None:
        """ Judge an answer and tell it: never raises, a failed judge is a judgment with an error """
        self.__bus.dispatch(EVAL_STARTED, id=job.sample.id)
        try:
            judgment: Judgment = self.__judge.judge(job.sample)
        except Exception as e:
            log.exception(f"[eval] judging {job.sample.id} failed")
            judgment = Judgment(job.sample, self.__judge.model, status="error", error=f"{type(e).__name__}: {e}")
        job.judgment = judgment
        job.done.set()
        log.info(f"[eval] {job.sample.id} judged in {judgment.duration}s: faithfulness {judgment.faithfulness}, "
                 f"relevance {judgment.relevance}, coherence {judgment.coherence}, {len(judgment.flagged)} flagged"
                 + (f", error: {judgment.error}" if judgment.error else ""))
        self.__bus.dispatch(EVAL_SCORED, **judgment.to_dict())
