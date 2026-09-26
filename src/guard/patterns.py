##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Patterns of the sensitive data: the ones the rails mask (through config/actions.py), and the log
##
## Plain regexes, without NeMo: cheap enough to run on every line of the log. Presidio does more on the
## messages (it reads the context), these ones only catch what has a fixed shape
##
import re

# French ids Presidio does not know. Numéro de sécurité sociale: 1 85 07 75 123 456 78 (2A/2B for Corsica)
NIR     : re.Pattern = re.compile(r"(?<!\d)[12] ?\d{2} ?(?:0[1-9]|1[0-2]) ?(?:\d{2}|2[AB]) ?\d{3} ?\d{3}(?: ?\d{2})?(?!\d)")
# 06 12 34 56 78, 06.12.34.56.78, +33 6 12 34 56 78
PHONE_FR: re.Pattern = re.compile(r"(?<![\d+])(?:\+33 ?|0)[1-9](?:[ .-]?\d{2}){4}(?!\d)")

# Secrets a file read by cat_file may hold (.env, keys): shown back, they leak
SECRET  : re.Pattern = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:.*?-----END [A-Z ]*PRIVATE KEY-----|.*)"   # the whole key
    r"|\bAKIA[0-9A-Z]{16}\b"                 # AWS access key
    r"|\bgh[pousr]_[A-Za-z0-9]{36}\b"        # GitHub token
    r"|\bsk-[A-Za-z0-9_-]{20,}",             # OpenAI, Anthropic... API keys
    re.DOTALL
)
# The value of a secret of a .env: DB_PASSWORD=hunter2. Upper case only, the way .env files write them:
# "password = input()" in some code is not one
ASSIGNED: re.Pattern = re.compile(r"\b([A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY)[A-Z0-9_]*\s*[=:]\s*)[^\s\"']+")

# What Presidio masks in the messages, for the log: emails, and the numbers whose checksum holds
EMAIL   : re.Pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
CARD    : re.Pattern = re.compile(r"(?<![\d-])\d(?:[ -]?\d){12,18}(?![\d-])")
IBAN    : re.Pattern = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")

def mask_french_ids(text: str) -> str:
    """ The text, its French ids replaced by their kind """
    return PHONE_FR.sub("<PHONE_NUMBER>", NIR.sub("<NIR>", text or ""))

def contains_secret(text: str) -> bool:
    """ Check if the text holds a secret """
    return SECRET.search(text or "") is not None

def redact(text: str) -> str:
    """ The text, everything sensitive replaced by its kind: what the log may keep """
    text = SECRET.sub("<SECRET>", text or "")
    text = ASSIGNED.sub(r"\1<SECRET>", text)
    text = EMAIL.sub("<EMAIL_ADDRESS>", text)
    text = IBAN.sub(lambda m: "<IBAN_CODE>" if _iban(m[0]) else m[0], text)
    text = CARD.sub(lambda m: "<CREDIT_CARD>" if _luhn(m[0]) else m[0], text)
    return mask_french_ids(text)

def _luhn(number: str) -> bool:
    """ Check the key of a card number: a timestamp or a count of tokens has none """
    digits: list[int] = [int(c) for c in number if c.isdigit()][::-1]
    return sum(d if i % 2 == 0 else (d * 2 - 9 if d > 4 else d * 2) for i, d in enumerate(digits)) % 10 == 0

def _iban(code: str) -> bool:
    """ Check the key of an IBAN (mod 97): an identifier in capitals has none """
    code = code.replace(" ", "")
    return int("".join(str(int(c, 36)) for c in code[4:] + code[:4])) % 97 == 1
