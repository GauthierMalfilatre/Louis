##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Shares: the documents published by a public link, kept in the database with the token of their link
##
from config.settings import settings
from guard.patterns import redact
from session.database import Database, now
from typing import Any
import json
import os
import secrets

# Bytes of randomness of a token (22 characters): the token is the only key of a link, it must never be guessed
TOKEN_BYTES: int = 16

# A token is typed back (/unshare) by its start, as /shares shows it: at least this many characters
MIN_PREFIX: int = 6

def base_url() -> str:
    """ Where the links point to: LOUIS_SHARE_URL, or the setting (the server of louis --serve) """
    return (os.environ.get("LOUIS_SHARE_URL") or settings.get("share.base_url", "http://localhost:8080")).rstrip("/")

def url(token: str) -> str:
    """ The public link of a share """
    return f"{base_url()}/s/{token}"

def masked(value: Any) -> tuple[Any, int]:
    """
        A value of the document with its sensitive data replaced by its kind (keys, passwords of a .env, emails,
        cards...), as the log keeps it: a public page never shows them. And how many texts were changed
    """
    if isinstance(value, str):
        hidden: str = redact(value)
        return hidden, int(hidden != value)
    if isinstance(value, list):
        pairs = [masked(item) for item in value]
        return [item for item, _ in pairs], sum(count for _, count in pairs)
    if isinstance(value, dict):
        pairs = {key: masked(item) for key, item in value.items()}
        return {key: item for key, (item, _) in pairs.items()}, sum(count for _, count in pairs.values())
    return value, 0

def create(db: Database, user_id: int, session_id: int | None, document: dict) -> str:
    """ Publish the document: its token, new at each share (a share is the document as it is now, never updated) """
    token: str = secrets.token_urlsafe(TOKEN_BYTES)
    db.execute(
        "INSERT INTO shares (token, user_id, session_id, kind, title, document, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (token, user_id, session_id, document["kind"], document["title"], json.dumps(document, ensure_ascii=False), now())
    )
    return token

def get(db: Database, token: str) -> dict | None:
    """ The document of a link, None if there is no such link or it was revoked """
    row = db.fetchone("SELECT document FROM shares WHERE token = ? AND revoked_at IS NULL", (token,))
    return json.loads(row["document"]) if row else None

def shares(db: Database, user_id: int) -> list[dict]:
    """ The links of the user still open, newest first, without their documents """
    rows = db.fetchall(
        "SELECT token, session_id, kind, title, created_at FROM shares "
        "WHERE user_id = ? AND revoked_at IS NULL ORDER BY created_at DESC, rowid DESC",
        (user_id,)
    )
    return [{**dict(row), "url": url(row["token"])} for row in rows]

def matching(db: Database, user_id: int, typed: str) -> list[str]:
    """
        The open links of the user a typed token names: the whole token, its link, or its start (MIN_PREFIX
        characters at least). Several if the start is not enough to tell them apart
    """
    token: str = typed.strip().rstrip("/").rsplit("/", 1)[-1]
    if len(token) < MIN_PREFIX:
        return []
    return [share["token"] for share in shares(db, user_id) if share["token"].startswith(token)]

def revoke(db: Database, user_id: int, token: str) -> bool:
    """ Close a link of the user: its page is gone from then on. False if it was not one of its open links """
    return db.execute(
        "UPDATE shares SET revoked_at = ? WHERE token = ? AND user_id = ? AND revoked_at IS NULL",
        (now(), token, user_id)
    ).rowcount == 1
