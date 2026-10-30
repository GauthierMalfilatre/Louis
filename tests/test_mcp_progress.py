##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of what an MCP server tells while it works: the progress of a long call, told to the user and waited for
## beyond the timeout (never beyond mcp.max_timeout), and its logs, written in the log of Louis at their level
##
import logging
import time
import pytest
from conftest import Person, fake
from events.event_list import MCP_PROGRESS
from interface.cli import mcp_progress
from model.reply import Reply
from tool.tool import failed
from tool.tool_call import ToolCall

def tools(manager) -> dict:
    return {tool.name: tool for tool in manager.tools()}

def steps(app) -> list[dict]:
    """ The steps of the long calls told to the user, as they come """
    told: list[dict] = []
    app.events.subscribe(lambda event: told.append(event.data), MCP_PROGRESS)
    return told

@pytest.fixture
def louis_log(monkeypatch, caplog):
    """ The log of Louis, read by the test """
    monkeypatch.setattr(logging.getLogger("louis"), "propagate", True)
    caplog.set_level(logging.DEBUG, logger="louis")
    return caplog

# Progress

def test_a_long_call_that_tells_how_far_it_is_is_waited_for_beyond_its_timeout(mcp, app):
    told = steps(app)
    start = time.monotonic()
    result = tools(mcp(fake(), timeout=0.5))["fake__progress"].handle(app, steps="4", delay="0.3")
    assert result == "fini" and time.monotonic() - start > 1.0
    assert [(step["progress"], step["total"], step["message"]) for step in told] == [
        (1, 4, "étape 1"), (2, 4, "étape 2"), (3, 4, "étape 3"), (4, 4, "étape 4")]
    assert {(step["tool"], step["server"]) for step in told} == {("fake__progress", "fake")}

def test_a_call_that_works_forever_is_not_waited_for_beyond_the_max_timeout(mcp, app):
    found = tools(mcp(fake(), timeout=0.5, **{"mcp.max_timeout": 0.8}))
    start = time.monotonic()
    result = found["fake__progress"].handle(app, steps="6", delay="0.3")
    assert failed(result) and "n'a pas répondu à progress en 0.8 s" in result
    assert time.monotonic() - start < 1.2
    # The server goes on: its late steps and answer are ignored
    time.sleep(1.2)
    assert found["fake__echo"].handle(app, text="encore") == "encore"

def test_the_steps_told_to_the_user_are_spaced_unless_the_server_says_something_new(mcp, app):
    told = steps(app)
    assert tools(mcp(fake()))["fake__progress"].handle(app, steps="6", delay="0.1", same="oui") == "fini"
    assert 1 <= len(told) <= 3 and told[0]["progress"] == 1

def test_how_far_a_call_is_is_one_line_for_the_user():
    assert mcp_progress({"progress": 3, "total": 10, "message": "Téléchargement"}) == "3/10 — Téléchargement"
    assert mcp_progress({"progress": 0.5, "total": None, "message": None}) == "0.5"
    assert mcp_progress({"progress": "?", "total": None, "message": None}) == "en cours"

def test_the_user_sees_the_progress_of_a_call_of_the_model(louis):
    user = Person()
    app = louis([fake()], [Reply(content="", tool_calls=[ToolCall("fake__progress", {"steps": "2", "delay": "0.6"})]),
                           Reply(content="C'est fini.")], user)
    app.answer("Travaille")
    assert [step["progress"] for step in user.seen(MCP_PROGRESS)] == [1, 2]

# Logs

def test_the_server_is_asked_for_its_logs_from_the_level_of_the_settings(mcp, app):
    assert tools(mcp(fake("fake", "--log")))["fake__level"].handle(app) == "info"
    assert tools(mcp(fake("debug", "--log"), **{"mcp.log_level": "debug"}))["debug__level"].handle(app) == "debug"
    # A server without logs is not asked
    assert tools(mcp(fake("quiet")))["quiet__level"].handle(app) == "<aucun>"
    assert tools(mcp(fake("none", "--log"), **{"mcp.log_level": None}))["none__level"].handle(app) == "<aucun>"

def test_the_logs_of_a_server_go_to_the_log_of_louis_at_their_level(mcp, app, louis_log):
    assert tools(mcp(fake("fake", "--log")))["fake__shout"].handle(app) == "crié"
    lines = [(record.levelno, record.getMessage()) for record in louis_log.records]
    assert (logging.WARNING, "[mcp] fake (fake): attention") in lines
    assert (logging.ERROR, '[mcp] fake (fake): {"code": 7}') in lines
