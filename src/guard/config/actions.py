##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Actions of the rails: the code the flows of rails.co call with "execute", loaded by NeMo itself.
## They only read a text and answer: no bus, no interface, no log of Louis (they run in the loop of NeMo)
##
import re
from nemoguardrails.actions import action

# French ids Presidio does not know. Numéro de sécurité sociale: 1 85 07 75 123 456 78 (2A/2B for Corsica)
NIR     : re.Pattern = re.compile(r"(?<!\d)[12] ?\d{2} ?(?:0[1-9]|1[0-2]) ?(?:\d{2}|2[AB]) ?\d{3} ?\d{3}(?: ?\d{2})?(?!\d)")
# 06 12 34 56 78, 06.12.34.56.78, +33 6 12 34 56 78
PHONE_FR: re.Pattern = re.compile(r"(?<![\d+])(?:\+33 ?|0)[1-9](?:[ .-]?\d{2}){4}(?!\d)")

# Secrets a file read by cat_file may hold (.env, keys): shown back, they leak
SECRET  : re.Pattern = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\bAKIA[0-9A-Z]{16}\b"                 # AWS access key
    r"|\bgh[pousr]_[A-Za-z0-9]{36}\b"        # GitHub token
    r"|\bsk-[A-Za-z0-9_-]{20,}"              # OpenAI, Anthropic... API keys
)

# async: NeMo runs them in its event loop, and warns about the synchronous ones
@action(name="mask_french_ids")
async def mask_french_ids(text: str) -> str:
    """ The text, its French ids replaced by their kind """
    return PHONE_FR.sub("<PHONE_NUMBER>", NIR.sub("<NIR>", text or ""))

@action(name="contains_secret")
async def contains_secret(text: str) -> bool:
    """ Check if the text holds a secret """
    return SECRET.search(text or "") is not None
