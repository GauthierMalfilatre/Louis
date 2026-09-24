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
    "chat.tools.maxdepth"  : 128,
    "chat.think"           : False,
    "chat.keepalive"       : "30m",
    # Tokens the model sees at once. 12288 keeps qwen3:8b at ~92% GPU on 8 GB of VRAM:
    # above that it spills onto the CPU, and gets much slower
    "chat.context"         : 12288,

}
