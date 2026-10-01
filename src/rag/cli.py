##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Index a folder without starting Louis:  louis --index ~/docs/python --name python
##
from interface.cli import CLI
from events.event_bus import EventBus
from rag.knowledge import Knowledge
from config.settings import settings
import os
import sys

def index_folder(path: str, name: str | None = None) -> int:
    """
        Index a folder, or bring it up to date: the same as /index, but for a big folder, that takes minutes, without
        loading the model of the chat. The events are shown by the CLI, as in a session. Ctrl+C keeps what was done
    """
    folder: str = os.path.realpath(os.path.expanduser(path))
    if not os.path.isdir(folder):
        sys.stderr.write(f"{path} n'est pas un dossier.\n")
        return 1
    bus: EventBus = EventBus()
    CLI().bind(bus)
    try:
        Knowledge.from_settings(settings, bus).index(folder, name)
    except KeyboardInterrupt:
        sys.stderr.write("\nInterrompu : les fichiers déjà indexés sont gardés, relance la commande pour finir.\n")
        return 130
    return 0
