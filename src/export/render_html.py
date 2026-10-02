##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## HTML export: the document as one page, whole in its file (no script, no internet), the base of the PDF
##
from export.render_md import SPEAKERS, SHORT_RESULT, ACTIONS, SOURCES, local
from interface.cli import LABELS, call_detail, result_summary, short_path
from markdown_it import MarkdownIt
from html import escape
import re

EXTENSION: str = "html"

# The replies of the model are Markdown: the HTML they hold is shown as text, never run (html False), and the links
# to javascript: and the like are left as text by markdown-it itself
MARKDOWN: MarkdownIt = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])

def tool(call: dict) -> str:
    """ A tool call on one line, as the terminal shows it, and its whole result folded below when it is long """
    name: str = call["name"]
    label: str = LABELS.get(name, name)
    detail: str = call_detail(name, call.get("arguments") or {})
    head: str = f"<b>{escape(label)}</b>" + (f" <code>{escape(detail)}</code>" if detail else "")
    result: str | None = call.get("result")
    if result is None:
        return f'<li class="call none"><span class="mark">○</span> {head} → sans résultat</li>'
    ok: bool = bool(call.get("ok"))
    line: str = (f'<span class="mark">{"✓" if ok else "✗"}</span> {head} '
                 f'<span class="summary">→ {escape(result_summary(name, result, ok))}</span>')
    folded: str = ""
    if "\n" in result.strip() or len(result.strip()) > SHORT_RESULT:
        folded = f"<details><summary>Résultat</summary><pre><code>{escape(result.rstrip())}</code></pre></details>"
    return f'<li class="call {"ok" if ok else "failed"}">{line}{folded}</li>'

def message(shown: dict) -> str:
    """ The body of one message: its text, then its tool calls """
    if shown["role"] == "tool":
        # A result without its call: its tool, and the result as it is
        return (f'<p class="meta">Résultat de <code>{escape(shown.get("name") or "?")}</code> :</p>'
                f'<pre><code>{escape(shown["content"].rstrip())}</code></pre>')
    content: str = shown["content"].strip()
    parts: list[str] = []
    if content:
        # The user types plain text, its lines as they are: the model writes Markdown
        parts.append(f'<p class="typed">{escape(content)}</p>' if shown["role"] == "user" else MARKDOWN.render(content))
    if shown.get("tools"):
        parts.append(f'<ul class="calls">{"".join(tool(call) for call in shown["tools"])}</ul>')
    return "".join(parts)

def artifact(file: dict) -> str:
    """ A file the model wrote: its path, what became of it, then its whole content """
    writes: int = file["writes"]
    about: list[str] = [ACTIONS.get(file["action"], file["action"]),
                        f"{writes} écriture{'s' if writes > 1 else ''}", SOURCES.get(file["source"], "")]
    body: str = ""
    if file["content"] is not None:
        language: str = f' class="language-{escape(file["language"])}"' if file["language"] else ""
        body = f"<pre><code{language}>{escape(file['content'].rstrip())}</code></pre>"
    return (f'<article class="file"><h3><code>{escape(file["path"])}</code></h3>'
            f'<p class="meta">{escape(" · ".join(part for part in about if part))}</p>{body}</article>')

def conversation(messages: list[dict]) -> str:
    """ The messages, one part per speaker: the rounds of tool calls of one answer stay under one "Louis" """
    parts: list[str] = []
    speaker: str | None = None
    for shown in messages:
        if shown["role"] != speaker or shown["role"] != "assistant":
            if speaker is not None:
                parts.append("</div></section>")
            at: str = local(shown.get("at"), "%H:%M")
            parts.append(f'<section class="turn {escape(shown["role"])}"><h2>{escape(SPEAKERS.get(shown["role"], shown["role"]))}'
                         f'{f" <time>{escape(at)}</time>" if at else ""}</h2><div class="body">')
            speaker = shown["role"]
        parts.append(message(shown))
    if speaker is not None:
        parts.append("</div></section>")
    return "".join(parts)

def render(document: dict) -> str:
    """ The page of the document: a title, what the session is, the conversation, then the files written """
    session: dict = document["session"]
    about: list[str] = [f"Session #{session['id']}" if session.get("id") is not None else "Session non enregistrée",
                        session.get("user") or "", local(session.get("created_at")), short_path(session.get("cwd") or "")]
    title: str = document["title"] or "Session Louis"
    files: str = "".join(artifact(file) for file in document.get("artifacts", []))
    if document.get("kind") == "artifact":
        main: str = files
    else:
        main = conversation(document["messages"])
        if files:
            main += f'<section class="files"><h2>Fichiers produits</h2>{files}</section>'
    values: dict[str, str] = {
        "TITLE"   : escape(title),
        "ABOUT"   : escape(" · ".join(part for part in about if part)),
        "EXPORTED": escape(local(document.get("exported_at"))),
        "MAIN"    : main,
    }
    # In one pass: a message that holds "__MAIN__" is never replaced in its turn
    return re.sub(r"__(TITLE|ABOUT|EXPORTED|MAIN)__", lambda found: values[found[1]], PAGE)

PAGE: str = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="Louis">
<title>__TITLE__</title>
<style>
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --border: rgba(11, 11, 11, 0.10); --wash: rgba(11, 11, 11, 0.04); --code: #f1f0ec;
  --user: #2a78d6; --good: #006300; --critical: #d03b3b;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --border: rgba(255, 255, 255, 0.10); --wash: rgba(255, 255, 255, 0.05); --code: #232322;
    --user: #3987e5; --good: #0ca30c; --critical: #e66767;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
  --border: rgba(255, 255, 255, 0.10); --wash: rgba(255, 255, 255, 0.05); --code: #232322;
  --user: #3987e5; --good: #0ca30c; --critical: #e66767;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 15px/1.55 system-ui, -apple-system, "Segoe UI", "DejaVu Sans", sans-serif; }
main { max-width: 860px; margin: 0 auto; padding: 32px 16px 64px; }
header h1 { font-size: 24px; font-weight: 600; margin: 0 0 6px; overflow-wrap: anywhere; }
.meta { color: var(--ink-2); font-size: 13px; margin: 0; }
code, pre { font: 13px/1.5 ui-monospace, "SF Mono", Menlo, Consolas, "DejaVu Sans Mono", monospace; }
:not(pre) > code { background: var(--code); border-radius: 4px; padding: 1px 5px; overflow-wrap: anywhere; }
pre { background: var(--code); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; overflow-x: auto; white-space: pre; }
pre code { background: none; padding: 0; }
.turn { margin-top: 22px; }
.turn h2 { font-size: 14px; font-weight: 600; margin: 0 0 6px; display: flex; gap: 8px; align-items: baseline; }
.turn h2 time { color: var(--muted); font-weight: 400; font-size: 12.5px; }
.turn.user .body { background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--user); border-radius: 8px; padding: 10px 14px; }
.turn .body > :first-child { margin-top: 0; }
.turn .body > :last-child { margin-bottom: 0; }
.typed { white-space: pre-wrap; overflow-wrap: anywhere; margin: 0; }
.body table { border-collapse: collapse; margin: 10px 0; display: block; overflow-x: auto; }
.body th, .body td { border: 1px solid var(--border); padding: 4px 10px; text-align: left; }
.body blockquote { margin: 10px 0; padding-left: 12px; border-left: 3px solid var(--border); color: var(--ink-2); }
.body a { color: var(--user); }
.calls { list-style: none; padding: 0; margin: 8px 0; font-size: 13.5px; }
.call { padding: 3px 0; overflow-wrap: anywhere; }
.call .mark { display: inline-block; width: 1.2em; }
.call.ok .mark { color: var(--good); }
.call.failed .mark { color: var(--critical); }
.call .summary { color: var(--ink-2); }
details { margin: 4px 0 4px 1.2em; }
summary { cursor: pointer; color: var(--ink-2); font-size: 12.5px; }
details pre { max-height: 420px; overflow: auto; margin: 6px 0; }
.files { margin-top: 36px; border-top: 1px solid var(--border); padding-top: 8px; }
.files > h2 { font-size: 18px; margin: 16px 0 0; }
.file { margin-top: 20px; }
.file h3 { font-size: 15px; margin: 0 0 2px; }
.file pre { margin-top: 8px; }
footer { margin-top: 40px; color: var(--muted); font-size: 12.5px; }
/* The PDF and the printed page: light, every result shown whole, nothing cut by a scrollbar */
@page { size: A4; margin: 16mm 14mm; }
@media print {
  :root, :root:not([data-theme="light"]) { color-scheme: light; --page: #ffffff; --surface: #ffffff; --ink: #0b0b0b; --ink-2: #52514e; --code: #f4f3ef; --border: rgba(11, 11, 11, 0.15); }
  main { max-width: none; padding: 0; }
  pre, details pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: none; overflow: visible; }
  .turn h2, .file h3 { break-after: avoid; }
}
</style>
</head>
<body>
<main>
<header>
<h1>__TITLE__</h1>
<p class="meta">__ABOUT__</p>
</header>
__MAIN__
<footer>Exportée de Louis le __EXPORTED__</footer>
</main>
</body>
</html>
"""
