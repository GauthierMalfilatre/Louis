##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Main file for the Sensai project
##
import sys
from interface.cli import CLI

def run() -> int:
    """ Run the main programm by creating the Application and running it """
    cli: CLI = CLI()

    while True:
        try:
            # Getting the user input
            u = cli.getUserInput()

            # Logging out the user input (stdout)
            cli.out(u)

            # Logging out the user input (stderr (as debug))
            cli.debug(f"User typing {u}")
        except KeyboardInterrupt:
            cli.debug("User has closed the session...\n")
            break

    return 0

if __name__ == "__main__":
    exitcode = run()
    sys.exit(exitcode)
