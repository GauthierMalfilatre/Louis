##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of web_search (T3): the query sent to DuckDuckGo, the results given to the model, and their way into the
## conversation. DuckDuckGo is faked: no network
##
import json
import pytest
import tool.impl.web.tool_websearch as websearch
from events.event_list import TOOL_CALL_ENDED
from model.reply import Reply
from tool.impl.web.tool_websearch import InternetTool
from tool.tool_call import ToolCall

RESULTS: list[dict] = [
    {"title": "Python 3.14 released", "href": "https://python.org/3.14", "body": "Python 3.14 is out."},
    {"title": "What's new", "href": "https://docs.python.org/whatsnew", "body": "Free-threaded build."},
]

@pytest.fixture
def searched(monkeypatch):
    """ DuckDuckGo answering RESULTS: the queries it was asked are kept """
    asked: list[tuple[str, int | None]] = []

    class DDGS:
        def text(self, query, max_results=None):
            asked.append((query, max_results))
            return RESULTS[:max_results] if max_results else RESULTS
    monkeypatch.setattr(websearch, "DDGS", DDGS)
    return asked

def test_the_results_are_given_as_json_title_url_and_snippet(searched):
    result = json.loads(InternetTool().handle(None, query="python 3.14", max_results=1))
    assert searched == [("python 3.14", 1)]
    assert result == [{"title": "Python 3.14 released", "url": "https://python.org/3.14", "snippet": "Python 3.14 is out."}]

def test_accents_are_kept_for_the_model_to_read(monkeypatch):
    class DDGS:
        def text(self, query, max_results=None):
            return [{"title": "Élysée", "href": "https://fr.wikipedia.org", "body": "Le palais de l'Élysée"}]
    monkeypatch.setattr(websearch, "DDGS", DDGS)
    assert "Élysée" in InternetTool().handle(None, query="élysée")

def test_the_schema_asks_for_a_query_only():
    parameters = InternetTool().schema["function"]["parameters"]
    assert parameters["required"] == ["query"] and set(parameters["properties"]) == {"query", "max_results"}

def test_the_model_searches_then_answers_from_the_results(chat, searched):
    app = chat([Reply(tool_calls=[ToolCall("web_search", {"query": "dernière version de Python"})]),
                Reply(content="La dernière version est Python 3.14 (python.org).")])
    app._App__answer("Quelle est la dernière version de Python ?")
    assert searched == [("dernière version de Python", None)]
    # The results are in the context of the next request
    result = app.sent[1]["messages"][-1]
    assert result["role"] == "tool" and "https://python.org/3.14" in result["content"]

def test_a_search_that_fails_is_an_error_the_model_reads(chat, monkeypatch):
    class DDGS:
        def text(self, query, max_results=None):
            raise RuntimeError("Ratelimit")
    monkeypatch.setattr(websearch, "DDGS", DDGS)
    app = chat([Reply(tool_calls=[ToolCall("web_search", {"query": "x"})]), Reply(content="La recherche a échoué.")])
    app._App__answer("Cherche x")
    [ended] = app.listener.seen(TOOL_CALL_ENDED)
    assert not ended["ok"] and "Ratelimit" in ended["result"]
