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
    # The context the request filled, as Ollama counted it: the prompt read, and what was generated
    tokens    : int            = 0
