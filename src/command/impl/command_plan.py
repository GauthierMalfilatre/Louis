##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## /plan: the plan of a risky reply shown before it acts (human in the loop), and from which risk on
##
from command.command import Command
from events.event_list import PLAN_SETTINGS
from tool.risk import REVERSIBLE, IRREVERSIBLE

# What the user may type, in French or English, with or without accents: the setting it changes
CHOICES: dict[str, tuple[str, object]] = {
    "on": ("hitl.enabled", True), "off": ("hitl.enabled", False),
    "irreversible": ("hitl.level", IRREVERSIBLE), "irréversible": ("hitl.level", IRREVERSIBLE),
    "reversible": ("hitl.level", REVERSIBLE), "réversible": ("hitl.level", REVERSIBLE),
}

USAGE: str = ("Usage : /plan [on|off|irreversible|reversible] : on et off montrent ou non le plan avant d'agir, "
              "irreversible seulement pour ce qui ne s'annule pas (un push, un merge), reversible pour toute modification.")

class PlanCommand(Command):
    def __init__(self):
        super().__init__(
            "plan",
            description="montre ton plan avant une action risquée, et attend ton accord (on, off, irreversible, reversible)",
            usage="[on|off|irreversible|reversible]"
        )

    def handle(self, app, arguments: str) -> None:
        """ Turn the plans on or off, or set from which risk on they are shown: without arguments, tell how it is """
        word: str = arguments.strip().lower()
        if word:
            if word not in CHOICES:
                self.error(app, "usage", USAGE)
                return
            key, value = CHOICES[word]
            app.settings[key] = value
            # Asking for a level means wanting the plans
            if key == "hitl.level":
                app.settings["hitl.enabled"] = True
        level: str = app.settings.get("hitl.level", IRREVERSIBLE)
        app.events.dispatch(PLAN_SETTINGS, enabled=bool(app.settings.get("hitl.enabled", True)),
                            level=level if level in (REVERSIBLE, IRREVERSIBLE) else IRREVERSIBLE)
