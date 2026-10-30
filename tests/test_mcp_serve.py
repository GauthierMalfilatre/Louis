##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Tests of Louis as an MCP server (louis --mcp-server): launched by a client as any server (here, Louis' own client),
## it offers its tools that only read, kept in the project; the knowledge base once something is indexed; and what
## goes wrong is an error for the client, never a crash, nor a line on its output that is not the protocol
##
import io
import json
import os
import sys
from config.settings import settings
from events.event_bus import EventBus
from rag.index import Index
from rag.knowledge import Knowledge
from tool.impl.file.tool_tree import TreeTool
from tool.mcp.serve import LouisServer, serve
from tool.mcp.tool_mcp import McpTool
from tool.risk import SAFE
from tool.tool import failed

MAIN: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "main.py")
LOUIS: dict = {"name": "louis", "command": sys.executable, "args": [MAIN, "--mcp-server"]}

def tools(manager) -> dict:
    return {tool.name: tool for tool in manager.tools()}

def conf(**extra) -> dict:
    """ The settings of a server in the test: no reranker to download, no Ollama to ask (keywords only) """
    return {**settings, "rag.enabled": True, "rag.rerank.enabled": False, "chat.uri": "http://127.0.0.1:9", **extra}

def ask(server: LouisServer, method: str, **params) -> dict:
    return server.answer({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})

# Launched by a client

def test_louis_offers_its_tools_that_read_to_a_client(mcp, app, folder, tmp_path):
    (folder / "notes.md").write_text("# Notes\n\nLe mot de passe du wifi est sur le frigo.\n")
    (tmp_path / "outside.txt").write_text("secret")
    manager = mcp(LOUIS, start_timeout=60.0)
    server = manager.server("louis")
    assert server.client.server_info["name"] == "louis"
    found = tools(manager)
    assert set(found) == {"louis__tree", "louis__cat_file", "louis__search"}
    assert all(tool.level == SAFE for tool in found.values())
    assert "frigo" in found["louis__cat_file"].handle(app, path="notes.md")
    assert "notes.md" in found["louis__tree"].handle(app, path=".")
    # Kept in the project
    outside = found["louis__cat_file"].handle(app, path="../outside.txt")
    assert failed(outside) and "en dehors du projet" in outside
    # Nothing that writes: edit_file is no tool of the server
    result = McpTool(server, {"name": "edit_file"}).handle(app, path="notes.md")
    assert failed(result) and "Unknown tool: edit_file" in result

# The knowledge base

def test_the_knowledge_base_is_offered_once_something_is_indexed(folder, tmp_path, monkeypatch):
    monkeypatch.setenv("LOUIS_RAG", str(tmp_path / "rag.db"))
    server = LouisServer(conf())
    assert "search_knowledge" not in [tool["name"] for tool in ask(server, "tools/list")["result"]["tools"]]
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "deploy.md").write_text("# Déploiement\n\nLe serveur de production s'appelle kiwi-prod-7.\n")
    Knowledge(EventBus(), Index(str(tmp_path / "rag.db")), None).index(str(docs), "docs")
    listed = {tool["name"]: tool for tool in ask(server, "tools/list")["result"]["tools"]}
    assert "docs" in listed["search_knowledge"]["description"]
    assert listed["search_knowledge"]["annotations"] == {"readOnlyHint": True, "openWorldHint": False}
    result = ask(server, "tools/call", name="search_knowledge", arguments={"query": "serveur de production"})["result"]
    assert not result["isError"] and "kiwi-prod-7" in result["content"][0]["text"]

# What goes wrong

def test_what_goes_wrong_in_a_tool_is_an_error_for_the_client(folder, monkeypatch):
    server = LouisServer(conf(**{"rag.enabled": False}))
    missing = ask(server, "tools/call", name="cat_file", arguments={})["result"]
    assert missing["isError"] and "'path' est requis" in missing["content"][0]["text"]
    def broken(self, app, **kwargs):
        raise RuntimeError("cassé")
    monkeypatch.setattr(TreeTool, "handle", broken)
    crashed = ask(server, "tools/call", name="tree", arguments={})["result"]
    assert crashed["isError"] and "RuntimeError : cassé" in crashed["content"][0]["text"]
    assert ask(server, "tools/call", name="ghost")["error"]["code"] == -32602

def test_the_protocol_of_the_server(folder):
    server = LouisServer(conf(**{"rag.enabled": False}))
    assert ask(server, "initialize", protocolVersion="2024-11-05")["result"]["protocolVersion"] == "2024-11-05"
    assert ask(server, "initialize", protocolVersion="1999-01-01")["result"]["protocolVersion"] == "2025-06-18"
    assert ask(server, "ping") == {"jsonrpc": "2.0", "id": 1, "result": {}}
    assert ask(server, "resources/list")["error"]["code"] == -32601
    assert server.answer({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None

def test_nothing_but_the_protocol_is_written_on_its_output(folder, monkeypatch, capsys):
    def noisy(self, app, **kwargs):
        print("une ligne qui n'est pas du JSON")
        return "arbre"
    monkeypatch.setattr(TreeTool, "handle", noisy)
    lines = ["{pas du json", json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "tree"}})]
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(lines) + "\n"))
    assert serve(conf(**{"rag.enabled": False})) == 0
    out, err = capsys.readouterr()
    replies = [json.loads(line) for line in out.splitlines()]
    assert [reply.get("error", {}).get("code") for reply in replies] == [-32700, None]
    assert replies[1]["result"]["content"][0]["text"] == "arbre"
    assert "une ligne qui n'est pas du JSON" in err
