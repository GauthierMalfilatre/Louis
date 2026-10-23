##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## A fake MCP server for the tests: tools of every risk, and one for each way a server can go wrong (too slow, a
## crash, an error), one that adds a tool (grow), one that tells how far it is (progress), started as Louis starts any
## server. Its options make it fail at its start, or give it more:
##   --fail-init  exits before it answers;  --mute  never answers;  --noise  writes a line that is not JSON first;
##   --pages      gives its tools over two pages of tools/list;  --log  has logs (logging/setLevel, shout)
##   --prompts    has prompts (greet, pair, empty, broken), and a tool that adds one (more_prompts)
##
import json
import os
import sys
import time

def tool(called: str, annotations: dict | None = None, **properties) -> dict:
    """ A tool of the server, its arguments all strings """
    spec: dict = {
        "name": called,
        "description": f"Outil {called} du faux serveur",
        "inputSchema": {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object",
                        "properties": {key: {"type": "string", "description": value} for key, value in properties.items()}},
    }
    if annotations is not None:
        spec["annotations"] = annotations
    return spec

TOOLS: list[dict] = [
    tool("echo", {"readOnlyHint": True}, text="Le texte renvoyé"),
    tool("gentle", {"readOnlyHint": False, "destructiveHint": False}),
    tool("act"),
    tool("fail", {"readOnlyHint": True}),
    tool("slow", {"readOnlyHint": True}, seconds="Secondes d'attente"),
    tool("crash", {"readOnlyHint": True}),
    tool("env", {"readOnlyHint": True}, name="La variable d'environnement"),
    tool("roots", {"readOnlyHint": True}),
    tool("picture", {"readOnlyHint": True}),
    tool("grow", {"readOnlyHint": True}),
    tool("progress", {"readOnlyHint": True}, steps="Étapes", delay="Secondes par étape", same="Le même message à chaque étape"),
    tool("level", {"readOnlyHint": True}),
    tool("shout", {"readOnlyHint": True}),
    tool("more_prompts", {"readOnlyHint": True}),
]

PROMPTS: list[dict] = [
    {"name": "greet", "description": "Salue quelqu'un", "arguments": [{"name": "name", "required": True}]},
    {"name": "pair", "description": "Deux messages", "arguments": [{"name": "first", "required": True},
                                                                   {"name": "second"}]},
    {"name": "empty", "description": "Aucun message"},
    {"name": "broken", "description": "Une erreur"},
]

def prompt(name: str, arguments: dict) -> dict:
    def said(role: str, text: str) -> dict:
        return {"role": role, "content": {"type": "text", "text": text}}
    match name:
        case "greet":
            return {"messages": [said("user", f"Dis bonjour à {arguments['name']}.")]}
        case "pair":
            return {"messages": [said("user", f"Premier : {arguments['first']}"),
                                 said("assistant", "Compris."),
                                 said("user", f"Second : {arguments.get('second', 'aucun')}")]}
        case "empty":
            return {"messages": []}
        case "added":
            return {"messages": [said("user", "Ajouté.")]}
    raise LookupError(f"Unknown prompt: {name}")

# The level of the logs the client asked for (logging/setLevel), None until it does
LEVEL: list[str | None] = [None]

def write(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()

def text(value: str, error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": value}], "isError": error}

def ask_client(method: str) -> dict:
    """ A request of the server to the client, mid-call: its answer """
    write({"jsonrpc": "2.0", "id": "server-1", "method": method})
    for line in sys.stdin:
        message = json.loads(line)
        if message.get("id") == "server-1":
            return message
    return {}

def log(level: str, data) -> None:
    write({"jsonrpc": "2.0", "method": "notifications/message", "params": {"level": level, "logger": "fake", "data": data}})

def call(name: str, arguments: dict, token=None) -> dict:
    match name:
        case "echo":
            return text(arguments.get("text", ""))
        case "gentle" | "act":
            return text(f"{name} : fait")
        case "fail":
            return text("ça n'a pas marché", error=True)
        case "slow":
            time.sleep(float(arguments.get("seconds", "5")))
            return text("enfin")
        case "crash":
            os._exit(3)
        case "env":
            return text(os.environ.get(arguments.get("name", ""), "<absente>"))
        case "roots":
            return text(json.dumps(ask_client("roots/list")))
        case "picture":
            return {"content": [{"type": "image", "data": "AAAA", "mimeType": "image/png"}], "isError": False}
        case "grow":
            # A new tool, and the client told its tools changed: before the answer, as a real server would
            TOOLS.append(tool("grown", {"readOnlyHint": True}))
            write({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})
            return text("un outil de plus")
        case "grown":
            return text("nouveau")
        case "progress":
            steps = int(arguments.get("steps", "3"))
            for step in range(1, steps + 1):
                time.sleep(float(arguments.get("delay", "0.1")))
                if token is not None:
                    message = "travail" if arguments.get("same") else f"étape {step}"
                    write({"jsonrpc": "2.0", "method": "notifications/progress",
                           "params": {"progressToken": token, "progress": step, "total": steps, "message": message}})
            return text("fini")
        case "level":
            return text(LEVEL[0] or "<aucun>")
        case "more_prompts":
            PROMPTS.append({"name": "added", "description": "Ajouté en cours de route"})
            write({"jsonrpc": "2.0", "method": "notifications/prompts/list_changed"})
            return text("un prompt de plus")
        case "shout":
            log("warning", "attention")
            log("error", {"code": 7})
            return text("crié")
    raise LookupError(f"Unknown tool: {name}")

def main() -> int:
    options: list[str] = sys.argv[1:]
    if "--fail-init" in options:
        sys.stderr.write("faux serveur : il manque sa clé d'API\n")
        return 2
    if "--noise" in options:
        print("faux serveur prêt", flush=True)
    for line in sys.stdin:
        message = json.loads(line)
        if "id" not in message or "--mute" in options:
            continue
        method, params = message.get("method"), message.get("params") or {}
        reply: dict = {"jsonrpc": "2.0", "id": message["id"]}
        if method == "initialize":
            capabilities = {"tools": {}, **({"logging": {}} if "--log" in options else {}),
                            **({"prompts": {"listChanged": True}} if "--prompts" in options else {})}
            reply["result"] = {"protocolVersion": params.get("protocolVersion"), "capabilities": capabilities,
                               "serverInfo": {"name": "fake", "version": "0"}}
        elif method == "logging/setLevel" and "--log" in options:
            LEVEL[0] = params.get("level")
            reply["result"] = {}
        elif method == "tools/list":
            if "--pages" not in options:
                reply["result"] = {"tools": TOOLS}
            elif params.get("cursor") == "2":
                reply["result"] = {"tools": TOOLS[3:]}
            else:
                reply["result"] = {"tools": TOOLS[:3], "nextCursor": "2"}
        elif method == "prompts/list" and "--prompts" in options:
            reply["result"] = {"prompts": PROMPTS}
        elif method == "prompts/get" and "--prompts" in options:
            try:
                reply["result"] = prompt(params.get("name"), params.get("arguments") or {})
            except LookupError as e:
                reply["error"] = {"code": -32602, "message": str(e)}
        elif method == "tools/call":
            try:
                reply["result"] = call(params.get("name"), params.get("arguments") or {},
                                       (params.get("_meta") or {}).get("progressToken"))
            except LookupError as e:
                reply["error"] = {"code": -32602, "message": str(e)}
        else:
            reply["error"] = {"code": -32601, "message": f"Method not found: {method}"}
        write(reply)
    return 0

if __name__ == "__main__":
    sys.exit(main())
