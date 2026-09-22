##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Model class def
##
import requests
from session.session import Session
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

        try:
            res = requests.post(
                f"{self.__uri}/api/show",
                json={"model": self.__model},
                timeout=5.0
            )
            if res.status_code != 200:
                raise ModelException(f"Unknown model {model}")
        except requests.RequestException:
            raise ModelException(f"Unknown model {model}")

    @property
    def model(self) -> str:
        """ Get the current model """
        return self.__model

    def switch(self, *, newuri = None, newmodel: str = None) -> None:
        """ Switch model """
        olduri, oldmodel = self.__uri, self.__model
        if newuri:
            self.__uri = newuri
        if newmodel:
            self.__model = newmodel
        try:
            res = requests.post(
                f"{self.__uri}/api/show",
                json={"model": self.__model},
                timeout=5.0
            )
            if res.status_code != 200:
                self.__uri, self.__model = olduri, oldmodel
                raise ModelException(f"Unknown model {newmodel}")
        except requests.RequestException:
            self.__uri, self.__model = olduri, oldmodel
            raise ModelException(f"Unknown model {newmodel}")


    def post(
            self: "Model",
            session: Session,
            content: str,
            *,
            role: str = "user",
            tools: list[dict[str]] = [],
            stream: bool = True
        ) -> dict[str]:
        """ Post a question to the model """
        if not self.__uri or not self.__model:
            raise ModelException("Bad uri or model name")
        session.stack(content, role=role)
        response: requests.Response = requests.post(
            f"{self.__uri}/api/chat",
            json={
                "model": self.__model,
                "messages": session.history,
                "tools": tools
            },
            stream=stream
        )
        response.raise_for_status()

        if not stream:
            jsoned = response.json()
            session.stack(jsoned["message"]["content"], role="assistant")
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
                    session.stack(resp_acc, role="assistant")
                    break
        return _stream_generator()
