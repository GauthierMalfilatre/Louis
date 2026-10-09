##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /eval: the scores of the last answer of Louis, and the claims its sources do not support
##
from command.command import Command
from events.event_list import EVAL_REPORT

class EvalCommand(Command):
    def __init__(self):
        super().__init__(
            "eval",
            description="note la dernière réponse (fidélité aux sources, pertinence, cohérence) et signale ses "
                        "affirmations non vérifiables ou contredites"
        )

    def handle(self, app, arguments: str) -> None:
        """ The judgment of the last answer: waited for if the judge is on it, asked now otherwise """
        judgment = app.evaluator.last()
        if judgment is None:
            self.error(app, "empty", "Aucune réponse à évaluer : pose d'abord une question à Louis.")
            return
        app.events.dispatch(EVAL_REPORT, **judgment.to_dict())
