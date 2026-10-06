##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Schemas: the JSON Schemas a structured reply must match, found by their name or their file
##
from config.settings import settings
from jsonschema.exceptions import SchemaError as InvalidSchema
from jsonschema.validators import validator_for
import json
import os

# The schemas of louis, given with it: those of the project come first, under the same name
LOUIS: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schemas")

class SchemaError(Exception):
    """ A schema that can not be used: not found, not JSON, or no JSON Schema. message says it to the user """
    def __init__(self, message: str):
        super().__init__(message)
        self.message: str = message

def project() -> str:
    """ The folder of the schemas of the project louis runs in: schemas/ by default """
    return os.path.join(os.getcwd(), settings.get("structured.dir", "schemas"))

def folders() -> list[tuple[str, str]]:
    """ Where the schemas are looked for, first one first: (folder, origin) """
    return [(project(), "projet"), (LOUIS, "louis")]

def is_path(name: str) -> bool:
    """ Whether a schema is given by its file (./todo.json, ~/schemas/todo.json) rather than by its name """
    return name.endswith(".json") or "/" in name or os.sep in name

# search a schemas in cwd first and after in louis schemas
def located(name: str) -> str | None:
    """ The file of a schema: the one given, or the first <name>.json of the folders. None if there is none """
    if is_path(name):
        path: str = os.path.abspath(os.path.expanduser(name))
        return path if os.path.isfile(path) else None
    return next(
        (
            path
            for folder, _ in folders()
            if os.path.isfile(
                path := os.path.join(folder, f"{name}.json")
            )
        ),
        None
    )

# if valid return true
def read(path: str) -> dict:
    """ The schema of a file, checked: raise SchemaError if it is not JSON, or not a JSON Schema """
    try:
        with open(path, "r", encoding="utf-8") as file:
            schema = json.load(file)
    except OSError as e:
        raise SchemaError(f"Impossible de lire {path} : {e.strerror or e}") from e
    except json.JSONDecodeError as e:
        raise SchemaError(f"{path} n'est pas du JSON valide (ligne {e.lineno} : {e.msg}).") from e
    if not isinstance(schema, dict):
        raise SchemaError(f"{path} n'est pas un schéma JSON : il doit être un objet {{...}}.")
    try:
        validator_for(schema).check_schema(schema)
    except InvalidSchema as e:
        where: str = "/".join(str(part) for part in e.path) or "la racine"
        raise SchemaError(f"{path} n'est pas un schéma JSON valide ({where} : {e.message}).") from e
    return schema

# return if find, name + corresponding schemas
def load(name: str) -> tuple[str, dict]:
    """ The name and the schema asked for, by its name (todo) or its file (./todo.json): raise SchemaError """
    path: str | None = located(name.strip())
    if path is None:
        names: str = ", ".join(schema["name"] for schema in available()) or "aucun"
        where: str = "ce fichier n'existe pas" if is_path(name) else \
            f"ni dans {settings.get('structured.dir', 'schemas')}/ ni dans les schémas de Louis"
        raise SchemaError(f"Schéma introuvable : {name} ({where}). Schémas disponibles : {names}.")
    return os.path.splitext(os.path.basename(path))[0], read(path)

# list of available schemas
def available() -> list[dict]:
    """
        The schemas that can be named, by name: {name, description, origin ("projet" or "louis"), path, ok}.
        One of the project hides the one of louis of the same name. A broken file is listed, not ok, with why
    """
    schemas: dict[str, dict] = {}
    for folder, origin in folders():
        if not os.path.isdir(folder):
            continue
        for file in sorted(os.listdir(folder)):
            name, extension = os.path.splitext(file)
            if extension != ".json" or name in schemas:
                continue
            path: str = os.path.join(folder, file)
            try:
                schema: dict = read(path)
                description: str = schema.get("description") or schema.get("title") or ""
                schemas[name] = {"name": name, "description": description, "origin": origin, "path": path, "ok": True}
            except SchemaError:
                schemas[name] = {"name": name, "description": f"invalide : /json {name} pour voir pourquoi",
                                 "origin": origin, "path": path, "ok": False}
    return list(schemas.values())
