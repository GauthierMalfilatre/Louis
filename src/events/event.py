##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Event Class
##
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class Event:
    """ Event class """
    name: str
    data: dict = field(default_factory=dict)
