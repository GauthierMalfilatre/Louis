##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Sample: one answer of Louis as the judge reads it, the question, the answer, and the sources its tools read
##
## The fields are those of a single turn of RAGAS (user_input, retrieved_contexts, response, reference): a sample
## saved by eval.bench can be given to RAGAS as it is (to_ragas)
##
from dataclasses import dataclass, field
import json

# Characters of the arguments of a call kept in the label of its source
LABEL_CHARS: int = 120

@dataclass(frozen=True, slots=True)
class Source:
    """ What a tool read for the answer: its arguments (masked with the guard, as shown) and its result """
    tool     : str
    arguments: dict
    text     : str

    def label(self) -> str:
        """ The source in one line, for the judge and the user: cat_file {"path": "src/app.py"} """
        arguments: str = json.dumps(self.arguments, ensure_ascii=False, default=str)
        if len(arguments) > LABEL_CHARS:
            arguments = arguments[:LABEL_CHARS - 1] + "…"
        return f"{self.tool} {arguments}"

@dataclass(slots=True)
class Sample:
    """
        One answer to judge. The texts are those the guard let through (the question masked, the results of the tools
        screened): the judge reads nothing the model or the user could not. model and prompt (its version) tell which
        Louis answered, to compare the versions
    """
    id       : str
    question : str
    answer   : str
    sources  : list[Source] = field(default_factory=list)
    model    : str | None   = None
    prompt   : str | None   = None
    session  : int | None   = None
    # The answer known to be right, for a question of a benchmark: none for a turn of the user
    reference: str | None   = None

    def to_ragas(self) -> dict:
        """ The sample as RAGAS reads it (SingleTurnSample) """
        return {
            "user_input": self.question,
            "retrieved_contexts": [source.text for source in self.sources],
            "response": self.answer,
            **({"reference": self.reference} if self.reference else {})
        }
