##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## calc: the MCP server of Louis, a calculator. A program of its own, launched by Louis as any other MCP server:
## it reads JSON-RPC on its standard input, one message per line, and answers on its standard output. Its tool
## calculates, its prompt (explain) asks the model to calculate step by step and explain
##
import ast
import json
import math
import operator
import sys

PROTOCOL_VERSION: str = "2025-06-18"

# What an expression may do: arithmetic and the functions of math, never a name or a call of Python beyond them
OPERATORS: dict = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}
FUNCTIONS: dict = {name: getattr(math, name) for name in (
    "sqrt", "cbrt", "exp", "log", "log2", "log10", "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "sinh",
    "cosh", "tanh", "degrees", "radians", "factorial", "gcd", "lcm", "floor", "ceil", "hypot", "comb", "perm",
) if hasattr(math, name)} | {"abs": abs, "round": round, "min": min, "max": max}
CONSTANTS: dict = {"pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf}

# Digits a result may have: beyond, a power would take the server minutes and its memory (9**9**9 has 370 million)
MAX_DIGITS: int = 100000
# The biggest number factorial, comb and perm take: factorial(25206) already has 100000 digits
MAX_FACTORIAL: int = 25000

TOOLS: list[dict] = [{
    "name": "calculate",
    "title": "Calculatrice",
    "description": (
        "Calcule exactement une expression mathématique et renvoie son résultat. Utilise-le pour tout calcul, "
        "plutôt que de le faire de tête : + - * / // % **, parenthèses, pi, e, et les fonctions sqrt, log, "
        "exp, sin, cos, tan, factorial, gcd, round, abs, min, max..."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "L'expression, par exemple '(3 + 4) * sqrt(16)'"}
        },
        "required": ["expression"],
    },
    "annotations": {"readOnlyHint": True, "openWorldHint": False},
}]

PROMPTS: list[dict] = [{
    "name": "explain",
    "title": "Expliquer un calcul",
    "description": "Calcule une expression avec la calculatrice, puis explique le résultat étape par étape",
    "arguments": [{"name": "expression", "description": "L'expression, par exemple '(3 + 4) * sqrt(16)'", "required": True}],
}]

def prompt(name: str, arguments: dict) -> dict:
    """ The messages of a prompt, written with its arguments """
    if name != "explain":
        raise LookupError(f"Unknown prompt: {name}")
    expression = arguments.get("expression")
    if not isinstance(expression, str) or not expression.strip():
        raise LookupError("Missing argument: expression")
    text: str = (f"Calcule {expression.strip()} avec l'outil calculate, sans le faire de tête. Puis explique le "
                 "résultat étape par étape : l'ordre des opérations, et la valeur de chaque étape.")
    return {"description": PROMPTS[0]["description"], "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}

def evaluate(node: ast.AST):
    """ The value of an expression, its nodes checked one by one: what is not arithmetic is refused """
    match node:
        case ast.Expression(body=body):
            return evaluate(body)
        case ast.Constant(value=value) if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        case ast.Name(id=name) if name in CONSTANTS:
            return CONSTANTS[name]
        case ast.UnaryOp(op=op, operand=operand) if type(op) in OPERATORS:
            return OPERATORS[type(op)](evaluate(operand))
        case ast.BinOp(left=left, op=op, right=right) if type(op) in OPERATORS:
            a, b = evaluate(left), evaluate(right)
            if isinstance(op, ast.Pow) and abs(a) > 1 and b > 0 and b * math.log10(abs(a)) > MAX_DIGITS:
                raise ValueError(f"résultat trop grand (plus de {MAX_DIGITS} chiffres)")
            return OPERATORS[type(op)](a, b)
        case ast.Call(func=ast.Name(id=name), args=args, keywords=[]) if name in FUNCTIONS:
            values = [evaluate(arg) for arg in args]
            if name in ("factorial", "comb", "perm") and any(abs(value) > MAX_FACTORIAL for value in values):
                raise ValueError(f"{name} ne va pas au-delà de {MAX_FACTORIAL}")
            return FUNCTIONS[name](*values)
    raise ValueError(f"« {ast.unparse(node)} » n'est pas permis dans un calcul")

def calculate(expression: str) -> str:
    """ The result of the expression, as text: an int stays exact, a float without its useless digits """
    value = evaluate(ast.parse(expression.strip(), mode="eval"))
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        value = int(value)
    return f"{expression.strip()} = {value}"

def call(name: str, arguments: dict) -> dict:
    """ The result of a tool: an error of the calculation is told to the model as such (isError), not as a failure """
    if name != "calculate":
        raise LookupError(f"Unknown tool: {name}")
    expression = arguments.get("expression")
    if not isinstance(expression, str) or not expression.strip():
        return {"content": [{"type": "text", "text": "Donne l'expression à calculer, dans 'expression'."}], "isError": True}
    try:
        return {"content": [{"type": "text", "text": calculate(expression)}], "isError": False}
    except ZeroDivisionError:
        text = "division par zéro"
    except SyntaxError as e:
        text = f"expression mal écrite ({e.msg})"
    except (ValueError, TypeError, OverflowError) as e:
        text = str(e)
    return {"content": [{"type": "text", "text": f"Calcul impossible : {text}."}], "isError": True}

def answer(message: dict) -> dict | None:
    """ The answer to a message of the client, None for a notification """
    method, params = message.get("method"), message.get("params") or {}
    if "id" not in message:
        return None
    reply: dict = {"jsonrpc": "2.0", "id": message["id"]}
    if method == "initialize":
        reply["result"] = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "prompts": {}},
            "serverInfo": {"name": "calc", "title": "Calculatrice de Louis", "version": "1.0"},
        }
    elif method == "ping":
        reply["result"] = {}
    elif method == "tools/list":
        reply["result"] = {"tools": TOOLS}
    elif method == "prompts/list":
        reply["result"] = {"prompts": PROMPTS}
    elif method == "prompts/get":
        try:
            reply["result"] = prompt(params.get("name"), params.get("arguments") or {})
        except LookupError as e:
            reply["error"] = {"code": -32602, "message": str(e)}
    elif method == "tools/call":
        try:
            reply["result"] = call(params.get("name"), params.get("arguments") or {})
        except LookupError as e:
            reply["error"] = {"code": -32602, "message": str(e)}
    else:
        reply["error"] = {"code": -32601, "message": f"Method not found: {method}"}
    return reply

def main() -> int:
    """ Answer the client until it closes the input of the server """
    # Python writes 4300 digits of an int at most, by default: as many as a result may have
    sys.set_int_max_str_digits(MAX_DIGITS + 1)
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            reply = answer(message) if isinstance(message, dict) else None
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0

if __name__ == "__main__":
    sys.exit(main())
