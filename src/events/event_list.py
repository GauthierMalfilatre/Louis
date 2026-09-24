##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Event list
##
TOOL_USAGE_STARTED = "tool.usage.started"
TOOL_USAGE_ENDED   = "tool.usage.ended"

# A tool asks before acting: the interface shows the request, and answers with the same id.
# Nobody answering means no: without an interface to ask the user, a tool never writes
TOOL_BEGFOR_PERMISSION = "tool.permission.begfor"   # data: id, tool, summary (one sentence), preview (a diff, or "")
TOOL_GRANT_PERMISSION  = "tool.permission.grant"    # data: id, granted

# What the commands tell the user. The data is raw and JSON-friendly (full texts, raw paths): each
# interface lays it out its own way, the CLI as text, a web page as it likes
SESSION_CREATED = "session.created"   # data: user, persistent (saved from the first message of the user on), custom_prompt
SESSION_LIST    = "session.list"      # data: user, sessions: [{id, first_message, cwd, here, current, created_at}]
SESSION_RESUMED = "session.resumed"   # data: id, user, messages (count), last_question, last_answer

COMMAND_UNKNOWN = "command.unknown"   # data: name, commands: [{name, usage, description}]
COMMAND_ERROR   = "command.error"     # data: command, reason (a short code), message (one sentence), details...
