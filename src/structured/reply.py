##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Structured replies: what the model is told of the schema, and whether its reply matches it
##
from jsonschema.validators import validator_for
from typing import Any
import json 

# Reasons kept of why a reply does not match: enough for the model to fix it, and for the user to read
MAX_ERRORS: int = 5

def instruction(schema: dict) -> str:
    """
        Put after the question: Ollama already constrains the reply to the schema, but the model fills it better
        when it reads it (the meaning of the fields, their descriptions)
    """
    return ("\n\nRéponds uniquement avec du JSON qui respecte ce schéma JSON, sans texte autour ni bloc de code. "
            "N'invente rien : si une information manque, mets null là où le schéma le permet.\n"
            f"{json.dumps(schema, ensure_ascii=False)}")

def checked(content: str, schema: dict) -> tuple[Any, list[str]]:
    """
        The JSON of a reply, and why it does not match the schema: [] when it does. The formats of the schema
        (date, email...) are checked too
    """
    try:
        data: Any = json.loads(content)
    except json.JSONDecodeError as e:
        return None, [f"ce n'est pas du JSON valide ({e.msg}, caractère {e.pos})"]
    validator = validator_for(schema)(schema, format_checker=validator_for(schema).FORMAT_CHECKER)
    errors = sorted(validator.iter_errors(data), key=lambda error: [str(part) for part in error.absolute_path])
    reasons: list[str] = [
        f"{'/'.join(str(part) for part in error.absolute_path) or '(racine)'} : {error.message}"
        for error in errors[:MAX_ERRORS]
    ]
    if len(errors) > MAX_ERRORS:
        reasons.append(f"et {len(errors) - MAX_ERRORS} autre{'s' if len(errors) - MAX_ERRORS > 1 else ''}")
    return data, reasons

def retry(errors: list[str]) -> str:
    """ Told to the model after a reply that does not match: what is wrong, for it to answer again """
    return ("Ta réponse ne respecte pas le schéma :\n" + "\n".join(f"- {error}" for error in errors) +
            "\nRéponds de nouveau, uniquement avec le JSON corrigé.")

def shown(data: Any) -> str:
    """ A structured reply as it is kept in the session: JSON in a code block, read as such by the exports """
    return f"```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```"
