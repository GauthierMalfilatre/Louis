##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /schemas: list the schemas /json can answer with
##
from command.command import Command
from events.event_list import SCHEMA_LIST
from structured.schema import available, project

class SchemasCommand(Command):
    def __init__(self):
        super().__init__("schemas", description="liste les schémas de /json : ceux du projet, puis ceux de Louis")

    def handle(self, app, arguments: str) -> None:
        """ Send the schemas that can be named, with where the project ones go """
        app.events.dispatch(SCHEMA_LIST, folder=project(), schemas=available())
