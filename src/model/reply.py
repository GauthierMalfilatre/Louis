##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Model Class
##
from dataclasses import dataclass

@dataclass
class Reply:
    content   : str            = ""
    # tool_calls: list[ToolCall] = field(default_factory=list)
