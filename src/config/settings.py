####
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Settings for the sensai project
##

settings: dict[str] = {

    "chat.stream"          : True,
    "chat.timeout.connect" : 5.0,
    "chat.timeout.response": 600.0,
    "chat.model.name"      : "qwen3",
    "chat.model.parameters": "8b",
    "chat.uri"             : "http://localhost:11434",
    "chat.tools.maxdepth"  : 40,
    "chat.think"           : False,
    "chat.keepalive"       : "30m",
    # Tokens the model sees at once. 12288 keeps qwen3:8b at ~92% GPU on 8 GB of VRAM:
    # above that it spills onto the CPU, and gets much slower
    "chat.context"         : 12288,
    # Tokens a reply may take at most: the room the context window leaves it (30 % of chat.context, see
    # app/context_window.py), less a margin for its estimate. Past it, a reply that never ends (a model going round
    # in circles) is cut, instead of overflowing the context. 3072 tokens: a file of about 300 lines for write_file
    "chat.predict"         : 3072,
    # Database of the sessions, in the working directory, unless LOUIS_DB gives another path:
    # the launcher of install.sh points it at the global one
    "db.file"              : "louis.db",

}
