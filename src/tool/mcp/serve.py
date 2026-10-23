##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Louis as an MCP server (louis --mcp-server): another client (Claude Code, Claude Desktop, MCP Inspector, another
## Louis...) launches it and gets the tools of Louis that only read: the files of the project (tree, cat_file,
## search) and the knowledge base the user indexed (search_knowledge). JSON-RPC on stdin and stdout, a line each
##
from logger.logger import log
from events.event_bus import EventBus
from rag.knowledge import Knowledge
from tool.tool import Tool, failed
from tool.seen_files import SeenFiles
from tool.impl.file.tool_tree import TreeTool
from tool.impl.file.tool_cat import CatTool
from tool.impl.file.tool_search import SearchTool
from tool.impl.rag.tool_knowledge import KnowledgeTool
from typing import TextIO
import json
import sys

# The versions of the protocol Louis speaks as a server, the latest first: a client gets its own if it is one of them
VERSIONS: tuple[str, ...] = ("2025-06-18", "2025-03-26", "2024-11-05")

INSTRUCTIONS: str = (
    "Louis lit le projet du dossier où il a été lancé : tree pour son arborescence, cat_file pour un fichier, search "
    "pour chercher un texte dans ses fichiers. search_knowledge, quand il est là, cherche dans la documentation et le "
    "code que l'utilisateur a indexés (louis --index). Ces outils ne font que lire."
)

class Refusal:
    """ No user to ask, as a server: a tool that asks is refused (none of those offered asks) """
    def request(self, tool: str, summary: str, preview: str = "", *, every_time: bool = False) -> bool:
        log.warning(f"[mcp-server] {tool} asked for a permission, refused: {summary}")
        return False

class Host:
    """ What the tools use of the app, for a server: the settings, the knowledge base; nobody to ask """
    def __init__(self, settings: dict, knowledge: Knowledge | None):
        self.settings   : dict             = settings
        self.knowledge  : Knowledge | None = knowledge
        self.permissions: Refusal          = Refusal()
        self.seen_files : SeenFiles        = SeenFiles()

class LouisServer:
    """ The tools of Louis that only read, offered to a client: the knowledge base only while something is indexed """
    def __init__(self, settings: dict):
        """ Init the server: the knowledge base of the settings, read in the working directory """
        knowledge: Knowledge | None = Knowledge.from_settings(settings, EventBus()) if settings.get("rag.enabled") else None
        self.__host     : Host          = Host(settings, knowledge)
        self.__tools    : list[Tool]    = [TreeTool(), CatTool(), SearchTool()]
        self.__knowledge: KnowledgeTool = KnowledgeTool()

    def tools(self) -> list[Tool]:
        """ The tools offered now: search_knowledge with what the base holds, if it holds something """
        knowledge: Knowledge | None = self.__host.knowledge
        if knowledge is None or knowledge.empty:
            return list(self.__tools)
        self.__knowledge.refresh(knowledge.catalog())
        return [*self.__tools, self.__knowledge]

    def answer(self, message: dict) -> dict | None:
        """ The answer to a message of the client, None for a notification """
        if "id" not in message:
            return None
        method, params = message.get("method"), message.get("params") or {}
        reply: dict = {"jsonrpc": "2.0", "id": message["id"]}
        if method == "initialize":
            asked = params.get("protocolVersion")
            reply["result"] = {
                "protocolVersion": asked if asked in VERSIONS else VERSIONS[0],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "louis", "title": "Louis", "version": "1.0"},
                "instructions": INSTRUCTIONS,
            }
        elif method == "ping":
            reply["result"] = {}
        elif method == "tools/list":
            reply["result"] = {"tools": [self.__spec(tool) for tool in self.tools()]}
        elif method == "tools/call":
            tool: Tool | None = next((tool for tool in self.tools() if tool.name == params.get("name")), None)
            if tool is None:
                reply["error"] = {"code": -32602, "message": f"Unknown tool: {params.get('name')}"}
            else:
                reply["result"] = self.__call(tool, params.get("arguments") or {})
        else:
            reply["error"] = {"code": -32601, "message": f"Method not found: {method}"}
        return reply

    @staticmethod
    def __spec(tool: Tool) -> dict:
        """ A tool as tools/list gives it: it only reads, and nothing outside of the machine """
        return {"name": tool.name, "description": tool.desc, "inputSchema": tool.schema["function"]["parameters"],
                "annotations": {"readOnlyHint": True, "openWorldHint": False}}

    def __call(self, tool: Tool, arguments: dict) -> dict:
        """ The result of a tool: what it could not do is an error for the client, never a crash of the server """
        log.info(f"[mcp-server] {tool.name} {json.dumps(arguments, ensure_ascii=False)[:300]}")
        try:
            result: str = str(tool.handle(self.__host, **arguments))
        except Exception as e:
            log.exception(f"[mcp-server] {tool.name} failed")
            result = f"Erreur : {tool.name} a échoué ({type(e).__name__} : {e})."
        return {"content": [{"type": "text", "text": result}], "isError": failed(result)}

    def serve(self, stdin: TextIO, stdout: TextIO) -> int:
        """ Answer the client until it closes the input of the server """
        for line in stdin:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
            else:
                reply = self.answer(message) if isinstance(message, dict) else None
            if reply is not None:
                stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
                stdout.flush()
        return 0

def serve(settings: dict) -> int:
    """
        Serve the tools of Louis on stdin and stdout. Whatever else would write on stdout (a library...) goes to stderr:
        the output is the protocol alone
    """
    protocol: TextIO = sys.stdout
    sys.stdout = sys.stderr
    log.info("[mcp-server] started")
    try:
        return LouisServer(settings).serve(sys.stdin, protocol)
    finally:
        log.info("[mcp-server] stopped")
