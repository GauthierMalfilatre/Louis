##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Model Class
##
from dataclasses import dataclass, field
from tool.tool_call import ToolCall

@dataclass
class Reply:
    content   : str            = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    # The reply reached the most tokens it may take (chat.predict): it was cut before its end
    cut       : bool           = False
    # What the request cost, as Ollama counted it: the tokens of the prompt it read, and of the reply it generated
    prompt_tokens    : int = 0
    completion_tokens: int = 0
    # Seconds until the first piece of the reply came (None if none did), then the ones Ollama took to load the model,
    # read the prompt and generate the reply
    ttft       : float | None = None
    load       : float        = 0.0
    prompt_eval: float        = 0.0
    generation : float        = 0.0
    # Why Ollama stopped: "stop", or "length" when the reply reached chat.predict
    done       : str | None   = None

    @property
    def tokens(self) -> int:
        """ The context the request filled: the prompt read, and what was generated """
        return self.prompt_tokens + self.completion_tokens
