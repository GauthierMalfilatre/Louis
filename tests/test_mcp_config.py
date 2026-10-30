##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of how the MCP servers are declared: the .mcp.json files (the format of Claude Code), the variables of the
## environment they name, the tools a declaration offers, a server disabled, and the servers of the project, started
## only once the user trusts them
##
import json
import os
import sys
import pytest
from conftest import CALC, FAKE, Person, fake
from events.event_list import MCP_CHANGED, MCP_STARTED, COMMAND_ERROR
from interface.cli import mcp_started
from tool.mcp.manager import RUNNING, FAILED, DISABLED, PENDING
from tool.tool import failed

def servers_file(path, **servers) -> str:
    """ A .mcp.json file that declares the servers given, as Claude Code writes it """
    path.write_text(json.dumps({"mcpServers": servers}))
    return str(path)

def fake_entry(*options: str, **extra) -> dict:
    """ The fake server, as a file declares it: its name is its key """
    return {"command": sys.executable, "args": [FAKE, *options], **extra}

def tools(manager) -> dict:
    return {tool.name: tool for tool in manager.tools()}

def states(manager) -> dict[str, str]:
    return {server.name: server.state for server in manager.servers}

def offered(app) -> set[str]:
    return {tool["function"]["name"] for tool in app._App__toolManager.all()}

# The files

def test_a_file_in_the_format_of_claude_code_declares_servers(mcp, tmp_path):
    path = servers_file(tmp_path / "mcp.json", fake=fake_entry(), calc={"command": CALC["command"], "args": CALC["args"],
                                                                         "description": "ignorée"})
    manager = mcp(**{"mcp.files": [path]})
    assert states(manager) == {"fake": RUNNING, "calc": RUNNING}
    assert {"fake__echo", "calc__calculate"} <= set(tools(manager))
    assert {server["source"] for server in manager.describe()} == {path}

def test_the_variables_of_the_environment_are_given_to_the_server(mcp, app, tmp_path, monkeypatch):
    monkeypatch.setenv("LOUIS_TEST_GREETING", "salut")
    monkeypatch.delenv("LOUIS_TEST_ABSENT", raising=False)
    path = servers_file(tmp_path / "mcp.json",
                        fake=fake_entry(env={"GREETING": "${LOUIS_TEST_GREETING}", "OTHER": "${LOUIS_TEST_ABSENT:-défaut}"}),
                        broken=fake_entry(env={"TOKEN": "${LOUIS_TEST_ABSENT}"}))
    manager = mcp(**{"mcp.files": [path]})
    env = tools(manager)["fake__env"]
    assert (env.handle(app, name="GREETING"), env.handle(app, name="OTHER")) == ("salut", "défaut")
    assert manager.server("broken").state == FAILED and "LOUIS_TEST_ABSENT n'est pas définie" in manager.server("broken").error

def test_a_server_of_a_file_replaces_the_one_declared_before_it(mcp, tmp_path):
    user = servers_file(tmp_path / "user.json", calc={"command": "louis-no-such-command"})
    other = servers_file(tmp_path / "other.json", calc={"command": CALC["command"], "args": CALC["args"]})
    manager = mcp({"name": "calc", "command": "louis-no-such-command"}, **{"mcp.files": [user, other]})
    assert [(server.name, server.state, server.declaration.source) for server in manager.servers] == [("calc", RUNNING, other)]

@pytest.mark.parametrize("content, why", [
    ('{"mcpServers": {', "fichier JSON invalide (ligne 1)"),
    ('{"servers": {}}', "mcpServers"),
    ('{"mcpServers": {"a": {"command": "x", "tools": "echo"}}}', "tools et exclude"),
    ('{"mcpServers": {"a": {"command": "x", "enabled": "no"}}}', "enabled"),
])
def test_a_file_that_is_not_valid_is_a_server_that_failed(mcp, tmp_path, content, why):
    (tmp_path / "mcp.json").write_text(content)
    manager = mcp(CALC, **{"mcp.files": [str(tmp_path / "mcp.json"), str(tmp_path / "absent.json")]})
    assert [server.state for server in manager.servers] == [RUNNING, FAILED]
    assert why in manager.servers[1].error

# What a declaration offers

def test_a_declaration_gives_its_server_a_timeout_of_its_own(mcp, app):
    manager = mcp(fake("hasty", timeout=0.3), fake("other"), timeout=5.0)
    assert (manager.server("hasty").timeout, manager.server("other").timeout) == (0.3, 5.0)
    result = tools(manager)["hasty__slow"].handle(app, seconds="1")
    assert failed(result) and "en 0.3 s" in result
    assert tools(manager)["other__slow"].handle(app, seconds="0.5") == "enfin"

def test_a_declaration_offers_the_tools_it_names_but_those_it_excludes(mcp):
    manager = mcp(fake("some", tools=["e*", "c*"], exclude=["crash"]), fake("all"))
    assert sorted(tool.remote for tool in manager.server("some").tools) == ["echo", "env"]
    hidden = manager.server("all").describe()["hidden"]
    assert hidden == 0 and manager.server("some").describe()["hidden"] == len(manager.server("all").tools) - 2

def test_a_server_disabled_is_not_started_until_the_user_starts_it(louis):
    user = Person()
    app = louis([fake(enabled=False), CALC], [], user)
    assert app.mcp.server("fake").state == DISABLED and app.mcp.server("fake").client is None
    assert "fake__echo" not in offered(app) and "calc__calculate" in offered(app)
    [started] = user.seen(MCP_STARTED)
    assert "fake : désactivé" in mcp_started(started["servers"])
    app._App__commands.fetch("/mcp restart fake", app)
    assert app.mcp.server("fake").state == RUNNING and "fake__echo" in offered(app)

# The servers of the project

@pytest.fixture
def project_file(folder):
    """ A .mcp.json in the project, that declares the fake server """
    return servers_file(folder / ".mcp.json", fake=fake_entry())

def test_a_server_of_the_project_waits_for_the_user_to_trust_it(louis, project_file, tmp_path):
    user = Person()
    app = louis([], [], user, **{"mcp.files": [".mcp.json"]})
    assert app.mcp.server("fake").state == PENDING and app.mcp.server("fake").client is None
    assert not any(name.startswith("fake__") for name in offered(app))
    [started] = user.seen(MCP_STARTED)
    assert "fake : attend ton accord (/mcp trust fake" in mcp_started(started["servers"])
    # Not started any other way
    app._App__commands.fetch("/mcp restart fake", app)
    assert [error["reason"] for error in user.seen(COMMAND_ERROR)] == ["pending"]
    app._App__commands.fetch("/mcp trust fake", app)
    assert app.mcp.server("fake").state == RUNNING and "fake__echo" in offered(app)
    assert [changed["change"] for changed in user.seen(MCP_CHANGED)] == ["trusted"]
    # Kept out of the project: the project can not trust itself
    trusted = json.loads((tmp_path / "mcp-trusted.json").read_text())
    assert list(trusted[os.path.realpath(os.getcwd())]) == ["fake"]
    app._App__commands.fetch("/mcp trust fake", app)
    assert user.seen(COMMAND_ERROR)[-1]["reason"] == "trusted"

def test_a_server_trusted_starts_with_louis_until_its_declaration_changes(louis, project_file, folder):
    first = louis([], [], Person(), **{"mcp.files": [".mcp.json"]})
    first._App__commands.fetch("/mcp trust fake", first)
    first.close()
    assert louis([], [], Person(), **{"mcp.files": [".mcp.json"]}).mcp.server("fake").state == RUNNING
    # Another command is another server: the user is asked again
    servers_file(folder / ".mcp.json", fake=fake_entry("--noise"))
    assert louis([], [], Person(), **{"mcp.files": [".mcp.json"]}).mcp.server("fake").state == PENDING

def test_a_trust_that_can_not_be_kept_is_told_and_the_server_waits(louis, project_file, tmp_path):
    (tmp_path / "file").write_text("")
    user = Person()
    app = louis([], [], user, **{"mcp.files": [".mcp.json"], "mcp.trust_file": str(tmp_path / "file" / "trusted.json")})
    app._App__commands.fetch("/mcp trust fake", app)
    assert user.seen(COMMAND_ERROR)[-1]["reason"] == "failed" and app.mcp.server("fake").state == PENDING

def test_the_servers_of_a_file_out_of_the_project_are_trusted(mcp, tmp_path):
    manager = mcp(**{"mcp.files": [servers_file(tmp_path / "user.json", fake=fake_entry())]})
    assert manager.server("fake").state == RUNNING
