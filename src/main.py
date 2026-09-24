##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Main file for the Sensai project
##
import sys
from interface.cli import CLI
from app.app import App
from config.settings import settings

def run() -> int:
    """ Run the main programm by creating the Application and running it """

    app: App = App(settings)

    res = app.run()
    return res

if __name__ == "__main__":
    exitcode = run()
    sys.exit(exitcode)
