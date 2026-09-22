settings: dict[str] = {
    "stream": True,
    "db_path": "sensai.db",
    "resume": True,  # Resume the user's last session instead of starting a new one
    "max_tool_rounds": 8,  # Model <-> tools round trips allowed for a single user message
}
