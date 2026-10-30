##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /cache: the semantic cache, the answers given again without the model
##
from command.command import Command
from events.event_list import CACHE_STATS, CACHE_ENABLED, CACHE_DISABLED

USAGE: str = "Usage : /cache pour le voir, /cache on|off pour l'activer ou le couper, /cache clear pour l'effacer, " \
             "/cache forget pour oublier la dernière réponse qu'il a donnée."

class CacheCommand(Command):
    def __init__(self):
        super().__init__(
            "cache",
            description="les réponses déjà données, rendues sans le modèle aux questions qui veulent dire la même chose",
            usage="[on|off|clear|forget]"
        )

    def handle(self, app, arguments: str) -> None:
        """ Show the cache, switch it on or off, clear the answers of the user, or forget the one served last """
        action: str = arguments.strip().lower()
        match action:
            case "":
                app.events.dispatch(CACHE_STATS, **app.cache.stats())
            case "on" | "off":
                app.cache.enabled = action == "on"
                app.events.dispatch(CACHE_ENABLED if app.cache.enabled else CACHE_DISABLED)
            case "clear":
                app.cache.clear()
            case "forget":
                if not app.cache.forget_last():
                    self.error(app, "nothing", "Le cache n'a donné aucune réponse depuis le lancement de Louis : rien à oublier.")
            case _:
                self.error(app, "usage", USAGE)
