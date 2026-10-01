##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## JSON export: the document as it is, to read again or to process
##
import json

EXTENSION: str = "json"

def render(document: dict) -> str:
    """ The document in JSON, readable: accents kept, indented """
    return json.dumps(document, ensure_ascii=False, indent=2, default=str) + "\n"
