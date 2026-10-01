##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /unshare: close a public link of the user, its page is gone from then on
##
from command.command import Command
from command.impl.command_share import ANONYMOUS
from events.event_list import SHARE_REVOKED
from logger.logger import log
from share.store import matching, revoke, url, MIN_PREFIX

class UnshareCommand(Command):
    def __init__(self):
        super().__init__("unshare", description="ferme un lien public, donné par /shares", usage="<lien>")

    def handle(self, app, arguments: str) -> None:
        """ Close the link named by its token, its address, or the start of its token """
        if app.user.is_anonymous:
            self.error(app, "anonymous", ANONYMOUS)
            return
        typed: str = arguments.strip()
        if not typed:
            self.error(app, "usage", f"Usage : /unshare <lien>, le lien ou au moins {MIN_PREFIX} caractères du "
                                     "jeton donné par /shares.")
            return
        tokens: list[str] = matching(app.user.db, app.user.id, typed)
        if not tokens:
            self.error(app, "not_found", f"Aucun de tes liens ouverts ne correspond à « {typed} » : tape /shares "
                                         f"pour les voir (au moins {MIN_PREFIX} caractères du jeton).", typed=typed)
            return
        if len(tokens) > 1:
            self.error(app, "ambiguous", f"{len(tokens)} de tes liens commencent par « {typed} » : "
                                         "donne plus de caractères du jeton.", typed=typed)
            return
        if not revoke(app.user.db, app.user.id, tokens[0]):
            self.error(app, "not_found", "Ce lien vient d'être fermé.", typed=typed)
            return
        log.info(f"[share] {tokens[0][:6]}… closed")
        app.events.dispatch(SHARE_REVOKED, token=tokens[0], url=url(tokens[0]))
