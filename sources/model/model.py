##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Model class def
##
import requests

class ModelException(Exception):
    def __init__(self, message: str = "Wrong Model usage"):
        self.message = message
        super.__init__(self.message)

class Model:
    def __init__(
            self,
            uri  : str | None = None,
            model: str | None = None
        ) -> "Model":
        """ Init model with given parameters """
        self.__uri    : str | None = uri
        self.__model  : str | None = model

        self.__history: list[dict[str]] = []

    def post(
            self: "Model",
            user: None,
            content: str,
            stream: bool = False
        ) -> dict[str]:
        """ Post a question to the model """
        if not self.__uri or not self.__model:
            raise ModelException("Bad uri or model name")
        self.__history.append({
            "role": "user",
            "content": content
        })
        response = requests.post(
            self.__uri,
            json={
                "model": self.__model,
                "messages": self.__history,
                "stream": stream
            }
        )
        return response.json()
