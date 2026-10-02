##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Model Exception Class
##

class ModelException(Exception):
    """ Model Exception """
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
