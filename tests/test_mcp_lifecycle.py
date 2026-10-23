##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of the life of an MCP server once Louis started: started again by itself after a crash, restarted or stopped
## by /mcp, and its tools listed again when it says they changed, offered to the model at the next message
##
from conftest import Person, fake
from events.event_list import MCP_CHANGED, COMMAND_ERROR
from interface.cli import mcp_changed
from model.reply import Reply
from tool.mcp.manager import RUNNING, CRASHED, STOPPED
from tool.tool import failed
from tool.tool_call import ToolCall

def tools(manager) -> dict:
    return {tool.name: tool for tool in manager.tools()}

def offered(app) -> set[str]:
    """ The tools the model is offered now """
    return {tool["function"]["name"] for tool in app._App__toolManager.all()}

# Started again by itself

def test_a_server_that_crashed_is_started_again_at_the_next_call_while_it_may(mcp, app):
    manager = mcp(fake(), restarts=1)
    server, found = manager.servers[0], tools(manager)
    crashed = found["fake__crash"].handle(app)
    # The call that saw the crash is never made again: it may have acted
    assert failed(crashed) and "Il sera relancé au prochain appel" in crashed
    assert server.state == CRASHED
    pid = server.client.pid
    # The tools made before the restart call the server as it is now
    assert found["fake__echo"].handle(app, text="relancé") == "relancé"
    assert server.state == RUNNING and server.client.pid != pid and server.restarts == 0
    # No restart left: it stays down
    assert "Fais sans cet outil" in found["fake__crash"].handle(app)
    after = found["fake__echo"].handle(app, text="là ?")
    assert failed(after) and "ne répond plus" in after and server.state == CRASHED

def test_a_server_stopped_is_never_started_again_by_itself(mcp, app):
    manager = mcp(fake(), restarts=3)
    server, found = manager.servers[0], tools(manager)
    server.stop()
    assert server.state == STOPPED and manager.tools() == []
    assert failed(found["fake__echo"].handle(app, text="x")) and server.state == STOPPED
    server.restart()
    assert server.state == RUNNING and found["fake__echo"].handle(app, text="de retour") == "de retour"

# Tools that change

def test_a_server_that_says_its_tools_changed_is_listed_again(mcp, app):
    manager = mcp(fake())
    assert "fake__grown" not in tools(manager)
    assert manager.refresh() == []
    tools(manager)["fake__grow"].handle(app)
    assert [(server.name, change) for server, change in manager.refresh()] == [("fake", "tools")]
    assert tools(manager)["fake__grown"].handle(app) == "nouveau"
    # Told once
    assert manager.refresh() == []

# In Louis

def test_the_model_is_offered_the_tools_a_server_added_at_the_next_message(louis):
    user = Person()
    app = louis([fake()], [Reply(content="", tool_calls=[ToolCall("fake__grow", {})]), Reply(content="Fait."),
                           Reply(content="Encore.")], user)
    app.answer("Ajoute un outil")
    assert all("fake__grown" not in names for names in app.offered)
    app.answer("Et maintenant ?")
    assert "fake__grown" in app.offered[-1]
    [changed] = user.seen(MCP_CHANGED)
    assert (changed["server"], changed["change"]) == ("fake", "tools")
    assert "fake__grown" in [tool["name"] for tool in changed["servers"][0]["tools"]]

def test_a_server_started_again_by_itself_is_told_at_the_next_message(louis):
    user = Person()
    app = louis([fake()], [
        Reply(content="", tool_calls=[ToolCall("fake__crash", {})]), Reply(content="Il a planté."),
        Reply(content="", tool_calls=[ToolCall("fake__echo", {"text": "ok"})]), Reply(content="Il répond."),
        Reply(content="Bien."),
    ], user, **{"mcp.restarts": 1})
    app.answer("Plante")
    app.answer("Réessaie")
    assert [message["content"] for message in app.session.history if message["role"] == "tool"][-1] == "ok"
    assert user.seen(MCP_CHANGED) == []
    app.answer("Merci")
    assert [(changed["server"], changed["change"]) for changed in user.seen(MCP_CHANGED)] == [("fake", "restarted")]

def test_mcp_stop_withdraws_the_tools_and_mcp_restart_offers_them_again(louis):
    user = Person()
    app = louis([fake()], [], user)
    assert "fake__echo" in offered(app)
    app._App__commands.fetch("/mcp stop fake", app)
    assert app.mcp.server("fake").state == STOPPED and not any(name.startswith("fake__") for name in offered(app))
    app._App__commands.fetch("/mcp restart fake", app)
    assert app.mcp.server("fake").state == RUNNING and "fake__echo" in offered(app)
    assert [changed["change"] for changed in user.seen(MCP_CHANGED)] == ["stopped", "restarted"]
    # Every command, for the completion of the interfaces
    assert "mcp" in [command["name"] for command in user.seen(MCP_CHANGED)[-1]["commands"]]

def test_mcp_restart_tells_what_it_can_not_do(louis):
    user = Person()
    app = louis([fake(), {"name": "bad"}], [], user)
    for typed in ("/mcp restart ghost", "/mcp jump fake", "/mcp restart", "/mcp restart bad"):
        app._App__commands.fetch(typed, app)
    assert [error["reason"] for error in user.seen(COMMAND_ERROR)] == ["unknown", "usage", "usage", "invalid"]
    assert "commande" in user.seen(COMMAND_ERROR)[-1]["message"]
    assert user.seen(MCP_CHANGED) == []

def test_what_happened_to_a_server_is_one_line_for_the_user():
    servers = [{"name": "calc", "state": RUNNING, "error": None, "tools": [{}]},
               {"name": "time", "state": "failed", "error": "la commande uvx est introuvable", "tools": []}]
    assert mcp_changed({"server": "calc", "change": "restarted", "servers": servers}) == ("MCP : calc relancé (1 outil)", True)
    assert mcp_changed({"server": "calc", "change": "tools", "servers": servers}) == ("MCP : calc a changé ses outils (1 outil)", True)
    assert mcp_changed({"server": "time", "change": "restarted", "servers": servers}) == \
        ("MCP : time n'a pas pu être relancé : la commande uvx est introuvable", False)
    assert mcp_changed({"server": "time", "change": "stopped", "servers": servers})[1]
