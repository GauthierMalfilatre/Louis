##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Document: a session as it is exported, the same for every format (JSON, Markdown, PDF...) and for a shared link
##
## The document is plain data, JSON-friendly: each format only lays it out.
##   {"v", "kind": "session", "title", "session": {id, user, cwd, created_at}, "exported_at", "messages", "artifacts"}
## A message is {"role": "user" | "assistant", "content", "at"}, and the replies of the model that call tools carry
## them: {"tools": [{"name", "arguments", "result", "ok"}]}, each with the result it got
##
from config.prompt import NUDGE_PROMPT
from session.database import now
from session.session import Session
from session.user import User
from tool.tool import failed

# Bumped when a field changes its meaning: an older export can be told apart, and read again by /import
VERSION: int = 1

# Characters of the first message of the user kept as the title
TITLE_LENGTH: int = 80

def title(messages: list[dict]) -> str:
    """ The first line of the first message of the user, shortened: what the session was about """
    first: str = next((message["content"] for message in messages if message["role"] == "user"), "")
    line: str = first.strip().split("\n", 1)[0].strip()
    return line if len(line) <= TITLE_LENGTH else line[:TITLE_LENGTH - 1].rstrip() + "…"

def conversation(session: Session) -> list[dict]:
    """
        The messages of the session as they are read: without the system prompt nor the nudges (Louis wrote them,
        not the user), and each tool result with the call it answers, in the reply of the model that asked for it
    """
    messages: list[dict] = []
    # The calls of the last reply of the model not answered yet, in the order they were made
    pending: list[dict] = []
    for message in session.messages:
        if message.role == "system" or (message.role == "user" and message.content == NUDGE_PROMPT):
            continue
        if message.role == "tool":
            if pending:
                call: dict = pending.pop(0)
                call["result"], call["ok"] = message.content, not failed(message.content)
            else:
                # A result without its call: never written by Louis, but kept rather than lost
                messages.append({"role": "tool", "content": message.content, "at": message.created_at,
                                 "name": message.tool_name})
            continue
        shown: dict = {"role": message.role, "content": message.content, "at": message.created_at}
        pending = []
        if message.role == "assistant" and message.tool_calls:
            shown["tools"] = [
                {"name": call.name, "arguments": call.arguments, "result": None, "ok": None}
                for call in message.tool_calls
            ]
            pending = list(shown["tools"])
        messages.append(shown)
    return messages

def build(session: Session, user: User) -> dict:
    """ The document of a session of the user, read from the database (or from memory for the anonymous one) """
    messages: list[dict] = conversation(session)
    return {
        "v"          : VERSION,
        "kind"       : "session",
        "title"      : title(messages),
        "session"    : {
            "id"        : session.id,
            "user"      : user.name,
            "cwd"       : session.cwd,
            "created_at": session.created_at,
        },
        "exported_at": now(),
        "messages"   : messages,
        # The files the model wrote in the session: collected in a later step
        "artifacts"  : [],
    }
