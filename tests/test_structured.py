##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the structured replies (T5): where the schemas are found, how a reply is checked against one, and /json
## asking again until the JSON matches. The model is a script of replies: no Ollama
##
import json
import pytest
import main
from events.event_list import STRUCTURED_REPLY, CHAT_TURN_ENDED, COMMAND_ERROR, SCHEMA_LIST
from model.reply import Reply
from structured.reply import checked, shown
from structured.schema import load, available, SchemaError

CONTACT: dict = {"nom": "Gauthier Malfilatre", "entreprise": "Sensai", "poste": "développeur",
                 "email": "gauthier.m@sensai.dev", "telephone": None}

def test_a_schema_is_found_by_its_name_the_project_ones_first(folder):
    name, schema = load("contact")
    assert name == "contact" and "nom" in schema["required"]
    (folder / "schemas").mkdir()
    (folder / "schemas/contact.json").write_text(json.dumps({"type": "object", "description": "le mien"}))
    assert load("contact")[1] == {"type": "object", "description": "le mien"}
    origins = {schema["name"]: schema["origin"] for schema in available()}
    assert origins["contact"] == "projet" and origins["todo"] == "louis" and origins["resume"] == "louis"

def test_a_schema_is_found_by_its_file_too(folder):
    (folder / "mine.json").write_text(json.dumps({"type": "array"}))
    assert load("./mine.json") == ("mine", {"type": "array"})

def test_a_schema_that_can_not_be_used_says_why(folder):
    (folder / "schemas").mkdir()
    (folder / "schemas/broken.json").write_text("{ pas du json")
    (folder / "schemas/wrong.json").write_text(json.dumps({"type": "nombre"}))
    with pytest.raises(SchemaError, match="Schéma introuvable : nope.*Schémas disponibles"):
        load("nope")
    with pytest.raises(SchemaError, match="n'est pas du JSON valide"):
        load("broken")
    with pytest.raises(SchemaError, match="n'est pas un schéma JSON valide"):
        load("wrong")
    broken = next(schema for schema in available() if schema["name"] == "broken")
    assert not broken["ok"]

def test_a_reply_is_checked_against_the_schema_and_its_formats():
    _, schema = load("contact")
    assert checked(json.dumps(CONTACT), schema) == (CONTACT, [])
    _, errors = checked(json.dumps({**CONTACT, "email": "pas-un-email", "age": 3}), schema)
    assert any(error.startswith("email :") for error in errors) and any("age" in error for error in errors)
    assert checked("Voici le JSON : {}", schema)[1][0].startswith("ce n'est pas du JSON valide")

def test_json_asks_again_with_the_errors_until_the_reply_matches(chat):
    app = chat([Reply(content=json.dumps({"nom": "Gauthier"})), Reply(content=json.dumps(CONTACT))])
    app._App__commands.fetch("/json contact Gauthier Malfilatre, développeur chez Sensai, gauthier.m@sensai.dev", app)
    first, second = app.sent
    # Ollama gets the schema to constrain the reply, and no tool
    assert first["schema"]["title"] == "Contact" and first["tools"] == []
    assert "Ta réponse ne respecte pas le schéma" in second["messages"][-1]["content"]
    [reply] = app.listener.seen(STRUCTURED_REPLY)
    assert (reply["valid"], reply["attempts"], reply["data"]) == (True, 2, CONTACT)
    # Kept as asked, the JSON in a code block
    assert app.session.history[-2]["content"].startswith("Gauthier Malfilatre")
    assert app.session.history[-1]["content"] == shown(CONTACT)

def test_a_reply_that_never_matches_is_an_error_never_given(chat):
    app = chat([Reply(content="{}")] * 2, **{"structured.attempts": 2})
    valid, data = app.structured("x", "contact", load("contact")[1])
    assert (valid, data) == (False, None)
    [ended] = app.listener.seen(CHAT_TURN_ENDED)
    assert ended["reason"] == "invalid" and "après 2 essais" in ended["message"]
    assert app.session.history[-1]["role"] == "user"

def test_json_and_schemas_tell_what_is_wrong_and_what_there_is(chat):
    app = chat([])
    for typed in ("/json", "/json nope question", "/json contact"):
        app._App__commands.fetch(typed, app)
    assert [error["reason"] for error in app.listener.seen(COMMAND_ERROR)] == ["usage", "schema", "usage"]
    app._App__commands.fetch("/schemas", app)
    [listing] = app.listener.seen(SCHEMA_LIST)
    assert {"contact", "todo", "resume"} <= {schema["name"] for schema in listing["schemas"]}

def test_ask_exits_2_for_a_schema_that_can_not_be_used(folder, capsys):
    assert main.ask("prompt", "Anonymous", "nope", "question") == 2
    assert "Schéma introuvable" in capsys.readouterr().err
