##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /json: answer a question with JSON that matches a schema, instead of text
##
from command.command import Command
from structured.schema import load, SchemaError

USAGE: str = ("Usage : /json <schéma> <question>, le schéma par son nom (/schemas pour les voir) "
              "ou par son fichier (./mon_schema.json).")

class JsonCommand(Command):
    def __init__(self):
        super().__init__(
            "json",
            description="répond en JSON qui respecte le schéma donné, au lieu de texte (sans outils)",
            usage="<schéma> <question>"
        )

    def handle(self, app, arguments: str) -> None:
        """ Answer the question with the JSON of the schema: the app tells the reply, or why it does not match """
        words: list[str] = arguments.strip().split(maxsplit=1)
        if not words:
            self.error(app, "usage", USAGE)
            return
        # The schema first: /json <schéma> alone tells what is wrong with it, as /schemas says
        try:
            name, schema = load(words[0])
        except SchemaError as e:
            self.error(app, "schema", e.message, schema=words[0])
            return
        if len(words) < 2:
            self.error(app, "usage", USAGE)
            return
        app.structured(words[1], name, schema)
