##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Model class def
##
import requests
from user.user import User 
import json
from collections.abc import Generator

class ModelException(Exception):
    def __init__(self, message: str = "Wrong Model usage"):
        self.message = message
        super().__init__(self.message)

class Model:
    def __init__(
            self,
            uri  : str | None = None,
            model: str | None = None
        ) -> "Model":
        """ Init model with given parameters """
        self.__uri    : str | None = uri
        self.__model  : str | None = model

    def post(
            self: "Model",
            user: User,
            content: str,
            *,
            stream: bool = True
        ) -> dict[str]:
        """ Post a question to the model """
        if not self.__uri or not self.__model:
            raise ModelException("Bad uri or model name")
        history: list[dict[str]] = user.stack(content)
        response: requests.Response = requests.post(
            self.__uri,
            json={
                "model": self.__model,
                "messages": history,
            },
            stream=stream
        )
        response.raise_for_status()

        if not stream:
            jsoned = response.json()
            user.stack(jsoned["message"]["content"], role="assistant")
            return jsoned

        # Stream generator
        def _stream_generator() -> Generator[str, None, None]:
            resp_acc = ""

            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                chunk = json.loads(line)
                text = chunk.get("message", {}).get("content", "")
                if text:
                    resp_acc += text
                    yield text
                if chunk.get("done", False):
                    user.stack(resp_acc, role="assistant")
                    break
        return _stream_generator()
