##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Context: where a passage is in its file, in one line read with its text by the embeddings, the keywords, the
## reranker and the model
##
## A passage cut in the middle of a function does not hold its name, nor the class it belongs to, nor the title of
## the section of a document it is in: "the main loop" does not find the body of run() that never says "def run".
## Its context says it: "class Trainer › def run(self, episodes=100) — Train the agent until it solves the task".
## Read from the file at indexing: Python by its syntax tree, Markdown by its titles, YAML by its keys, the other
## code by its indentation. A file that says nothing of it (a text, data) has passages without context
##
from rag.chunker import Chunk
from rag.index import kind_of
import ast
import os
import re

# Each piece of a context is cut to this, and the whole context to CONTEXT: it goes with every passage
LABEL  : int = 80
DOC    : int = 100
CONTEXT: int = 240
# Definitions starting in a passage named in its context at most (the passage holds them, not their class)
INSIDE : int = 3
# Lines read back from a passage to find the definition it is in, in a file read by its indentation
LOOK_BACK: int = 2000

SEPARATOR: str = " › "

def contexts(path: str, text: str, chunks: list[Chunk]) -> list[str]:
    """ The context of each passage of a file, "" when nothing is known of it """
    extension: str = os.path.splitext(path)[1].lower()
    lines: list[str] = text.splitlines()
    if extension in (".py", ".pyi"):
        found: list[str] | None = python(text, chunks)
        if found is not None:
            return found
    if extension in (".md", ".markdown"):
        return titles(lines, chunks)
    if extension in (".yml", ".yaml"):
        return keys(lines, chunks)
    if kind_of(path) == "code" and extension != ".ipynb":
        return [indented(lines, chunk) for chunk in chunks]
    return [""] * len(chunks)

def header(path: str, context: str) -> str:
    """ The first line of a passage as the embeddings read it: its file, and where it is in it """
    return f"{path.lstrip('/')}{SEPARATOR}{context}" if context else path.lstrip("/")

def brief(context: str) -> str:
    """
        The context as the reranker reads it: without the arguments of the functions nor the list of the definitions
        a passage holds. It reads a passage up to rag.rerank.max_chars: each character of context is one of code less.
        Measured: as good as the whole context, better than none on the questions with no answer (docs/RAG.md)
    """
    context = re.sub(r"\s*\[[^\]]*\]", "", context)
    return re.sub(r"\((?:[^()]|\([^()]*\))*\)", "", context).strip()

def cut(text: str, most: int) -> str:
    """ A text on one line, cut to most characters """
    text = " ".join(text.split())
    return text if len(text) <= most else text[:most - 1] + "…"

# --- Python: the syntax tree gives where each class and function starts and ends ---

def python(text: str, chunks: list[Chunk]) -> list[str] | None:
    """ The classes and functions each passage is in, or holds; None if the file does not parse """
    try:
        tree: ast.Module = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    # (start, end, label, first line of the docstring)
    definitions: list[tuple[int, int, str, str]] = sorted(
        (node.lineno, node.end_lineno or node.lineno, label(node), doc(node))
        for node in ast.walk(tree) if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    )
    # The definition each one is right inside (None: at the top of the file): the last one starting before it that
    # ends after it, the definitions being sorted by their start
    parents: list[int | None] = [
        next((j for j in range(i - 1, -1, -1) if definitions[j][0] < start and definitions[j][1] >= end), None)
        for i, (start, end, _, _) in enumerate(definitions)
    ]
    found: list[str] = []
    for chunk in chunks:
        # Nested definitions are nested spans: those holding the first line, the outer one first
        held: list[int] = [i for i, d in enumerate(definitions) if d[0] <= chunk.start <= d[1]]
        chain = [definitions[i] for i in held]
        inner: tuple | None = chain[-1] if chain else None
        # The definitions starting in the passage, right inside one it is in or at the top of the file: the next
        # method of the class, the next class (not the methods of a definition the passage holds)
        inside = [d for i, d in enumerate(definitions)
                  if chunk.start < d[0] <= chunk.end and (parents[i] is None or parents[i] in held)]
        parts: list[str] = [d[2] for d in chain]
        context: str = SEPARATOR.join(parts)
        if inside:
            names: str = ", ".join(d[2].split("(")[0] for d in inside[:INSIDE]) + (", …" if len(inside) > INSIDE else "")
            context += (" " if context else "") + f"[{names}]"
        docstring: str = (inner[3] if inner else "") or (inside[0][3] if inside else "")
        if docstring:
            context += f" — {docstring}"
        found.append(cut(context, CONTEXT))
    return found

def label(node: ast.AST) -> str:
    """ "class Name", "def name(arguments)" """
    if isinstance(node, ast.ClassDef):
        return f"class {node.name}"
    prefix: str = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    try:
        arguments: str = ast.unparse(node.args)
    except Exception:
        arguments = "…"
    return cut(f"{prefix} {node.name}({arguments})", LABEL)

def doc(node: ast.AST) -> str:
    """ The first line of the docstring of a class or a function, "" without one """
    docstring: str | None = ast.get_docstring(node, clean=True)
    first: str = next((line for line in (docstring or "").splitlines() if line.strip()), "")
    return cut(first, DOC)

# --- Markdown: the titles above a passage ---

TITLE: re.Pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE: re.Pattern = re.compile(r"^\s*(```|~~~)")

def titles(lines: list[str], chunks: list[Chunk]) -> list[str]:
    """ The titles each passage is under, the biggest first: "Guide › Install › Linux" """
    starts: dict[int, list[int]] = {}
    for i, chunk in enumerate(chunks):
        starts.setdefault(chunk.start, []).append(i)
    found: list[str] = [""] * len(chunks)
    stack: list[tuple[int, str]] = []
    fenced: bool = False
    # One pass: the titles in force at each first line of a passage
    for number, line in enumerate(lines, 1):
        for i in starts.get(number, []):
            found[i] = cut(SEPARATOR.join(title for _, title in stack), CONTEXT)
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced and (match := TITLE.match(line)):
            level: int = len(match[1])
            stack = [(depth, title) for depth, title in stack if depth < level] + [(level, cut(match[2], LABEL))]
    return found

# --- YAML: the key of the top level a passage is under ---

TOP_KEY: re.Pattern = re.compile(r"^([^\s#][^:#]*?):(\s.*|)$")

def keys(lines: list[str], chunks: list[Chunk]) -> list[str]:
    """ The key of the top level each passage starts under ("" before the first one) """
    starts: dict[int, list[int]] = {}
    for i, chunk in enumerate(chunks):
        starts.setdefault(chunk.start, []).append(i)
    found: list[str] = [""] * len(chunks)
    current: str = ""
    for number, line in enumerate(lines, 1):
        if (match := TOP_KEY.match(line)) and not line.startswith("- "):
            current = cut(match[1].strip("'\" "), LABEL)
        for i in starts.get(number, []):
            found[i] = current
    return found

# --- Other code: the less indented lines above that look like a definition ---

DEFINITION: re.Pattern = re.compile(
    r"^\s*(?:(?:export|public|private|protected|internal|static|async|pub(?:\([^)]*\))?|override|abstract|final|"
    r"virtual|inline|extern|unsafe|default|sealed|open|suspend)\s+)*"
    r"(?:def|class|function|fn|func|struct|impl|interface|enum|trait|module|namespace|type|object|record|union|"
    r"protocol|extension|sub|procedure|macro_rules!)\b"
)
# "int main(int argc, char **argv)", "static void *worker(void *arg) {", "public String getName() {"
SIGNATURE: re.Pattern = re.compile(r"^\s*[\w:<>\*&\[\],\s]*?[\w>\*&\]]\s+\**\s*([A-Za-z_][\w:~]*)\s*\([^;]*\)?\s*(?:const\s*)?\{?\s*$")
CONTROL: frozenset[str] = frozenset({"if", "for", "while", "switch", "return", "else", "catch", "do", "case", "sizeof"})
# Lines that say nothing of where the code is: a brace alone, a comment
PUNCTUATION: re.Pattern = re.compile(r"^\s*[{}()\[\];,]*\s*$")
COMMENT: re.Pattern = re.compile(r"^\s*(//|#|/\*|\*|--|;)")

def indented(lines: list[str], chunk: Chunk) -> str:
    """ The definitions a passage is in, read back from its first line: each less indented than the one below """
    first: str = next((line for line in lines[chunk.start - 1:chunk.end] if line.strip()), "")
    limit: int = len(first) - len(first.lstrip())
    chain: list[str] = []
    for line in reversed(lines[max(0, chunk.start - 1 - LOOK_BACK):chunk.start - 1]):
        if limit == 0:
            break
        if not line.strip() or PUNCTUATION.match(line) or COMMENT.match(line):
            continue
        indent: int = len(line) - len(line.lstrip())
        if indent >= limit:
            continue
        # A block the passage is in: a definition is said, a loop or a condition only lowers the limit
        signature = SIGNATURE.match(line)
        if DEFINITION.match(line) or (signature and signature[1] not in CONTROL):
            chain.insert(0, cut(line.strip().rstrip("{:").strip(), LABEL))
        limit = indent
    return cut(SEPARATOR.join(chain), CONTEXT)
