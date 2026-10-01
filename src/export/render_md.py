##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Markdown export: the document as a page to read, on GitHub, in an editor or a Markdown viewer
##
## The replies of the model are written as they are (they are Markdown already). The tool calls are one line each,
## as the terminal shows them, and their whole result is folded below (<details>): a file read stays at hand
## without burying the conversation
##
from interface.cli import LABELS, call_detail, result_summary, short_path
from datetime import datetime, timezone
import html
import re

EXTENSION: str = "md"

# Who wrote a message, as the title of its part
SPEAKERS: dict[str, str] = {"user": "Toi", "assistant": "Louis", "tool": "Outil"}

# Up to this, the line of the call says the whole result: nothing is folded below it
SHORT_RESULT: int = 70

def local(at: str | None, shown: str = "%d/%m/%Y %H:%M") -> str:
    """ A time of the database (UTC) in the time of the reader, "" if there is none """
    if not at:
        return ""
    try:
        return datetime.strptime(at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone().strftime(shown)
    except ValueError:
        return at

def ticks(text: str) -> int:
    """ The longest run of backticks in text: a code block or span around it needs more of them """
    return max((len(run) for run in re.findall(r"`+", text)), default=0)

def code(text: str) -> str:
    """ text as inline code, whatever backticks it holds """
    marks: str = "`" * (ticks(text) + 1)
    padded: str = f" {text} " if text.startswith("`") or text.endswith("`") else text
    return f"{marks}{padded}{marks}"

def block(text: str) -> str:
    """ text as a code block, never closed early by a ``` inside it """
    marks: str = "`" * max(3, ticks(text) + 1)
    return f"{marks}\n{text.rstrip()}\n{marks}"

def kept_lines(text: str) -> str:
    """
        A message of the user with its lines as typed: Markdown joins the lines of a paragraph, a line ending with
        two spaces breaks it. Not in a code block, which keeps its lines already
    """
    lines: list[str] = []
    fenced: bool = False
    for line in text.split("\n"):
        if re.match(r" {0,3}(`{3,}|~{3,})", line):
            fenced = not fenced
        lines.append(line if fenced or not line.strip() else line.rstrip() + "  ")
    return "\n".join(lines).rstrip()

def tool(call: dict) -> tuple[str, str | None]:
    """ The line of a tool call, and its whole result folded below when the line does not say all of it """
    name: str = call["name"]
    label: str = LABELS.get(name, name)
    detail: str = call_detail(name, call.get("arguments") or {})
    head: str = f"{label} {code(detail)}" if detail else label
    result: str | None = call.get("result")
    if result is None:
        return f"- ○ {head} → sans résultat", None
    line: str = f"- {'✓' if call.get('ok') else '✗'} {head} → {result_summary(name, result, bool(call.get('ok')))}"
    if "\n" not in result.strip() and len(result.strip()) <= SHORT_RESULT:
        return line, None
    summary: str = html.escape(f"Résultat : {label} {detail}".rstrip())
    return line, f"<details><summary>{summary}</summary>\n\n{block(result)}\n\n</details>"

def message(shown: dict) -> list[str]:
    """ The blocks of one message: its text, then its tool calls and their results """
    if shown["role"] == "tool":
        # A result without its call: its tool, and the result as it is
        return [f"Résultat de {code(shown.get('name') or '?')} :", block(shown["content"])]
    # The replies of the model are Markdown already: those of the user are plain text
    content: str = kept_lines(shown["content"].strip()) if shown["role"] == "user" else shown["content"].strip()
    parts: list[str] = [content] if content else []
    calls: list[tuple[str, str | None]] = [tool(call) for call in shown.get("tools", [])]
    if calls:
        parts.append("\n".join(line for line, _ in calls))
        parts += [folded for _, folded in calls if folded]
    return parts

def render(document: dict) -> str:
    """ The document as Markdown: a title, what the session is, then the conversation, one part per speaker """
    session: dict = document["session"]
    about: list[str] = [f"Session #{session['id']}" if session.get("id") is not None else "Session non enregistrée",
                        session.get("user") or "", local(session.get("created_at")), short_path(session.get("cwd") or "")]
    blocks: list[str] = [
        f"# {document['title'] or 'Session Louis'}",
        f"*{' · '.join(part for part in about if part)}*  \n*Exportée le {local(document.get('exported_at'))}*",
        "---",
    ]
    speaker: str | None = None
    for shown in document["messages"]:
        # The rounds of tool calls of one answer are as many replies of the model: one part for all of them
        if shown["role"] != speaker or shown["role"] != "assistant":
            at: str = local(shown.get("at"), "%H:%M")
            blocks.append(f"### {SPEAKERS.get(shown['role'], shown['role'])}{f' · {at}' if at else ''}")
            speaker = shown["role"]
        blocks += message(shown)
    return "\n\n".join(blocks) + "\n"
