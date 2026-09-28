##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Event list
##
# The thinking mode of the model, switched by /think: it thinks before every reply from then on
THINKING_ENABLED  = "chat.thinking.enabled"    # data: none
THINKING_DISABLED = "chat.thinking.disabled"   # data: none

# The conversation, as it goes: the app never prints, the interfaces show these their own way
CHAT_TURN_STARTED = "chat.turn.started"   # data: none (the model starts answering a message of the user)
CHAT_TURN_ENDED   = "chat.turn.ended"     # data: reason ("done", "cancelled", "error", "rounds", "loop", "length", "refused"), message (None when done or cancelled)
CHAT_TEXT         = "chat.text"           # data: text (a piece of the reply, as the model writes it)
CHAT_REPLY        = "chat.reply"          # data: content (the whole reply, "" if it only calls tools), tools (their names)
CHAT_NUDGED       = "chat.nudged"         # data: none (the model announced an action without doing it: it is told to)
# How full the context of the model is: measured by Ollama after each reply, estimated when the session changes
CHAT_CONTEXT      = "chat.context"        # data: used, size (tokens), estimated
CHAT_THINKING     = "chat.thinking.text"  # data: text (a piece of what the model thinks before replying, with /think)
# The context filled up: the old tool results were cut down to their first lines (the model may ask for them again),
# and at last the oldest exchanges left out. What is saved of the session stays whole
CHAT_COMPACTED    = "chat.compacted"      # data: results (cut down this time), dropped (messages left out this time), used, size (tokens)

# One request to the model, however it went: what the monitoring records. status is "ok", "error" (error tells why) or
# "cancelled" (Ctrl+C); latency the seconds of the whole request; system the prompt of the session, without the context
# put after it (the date changes it every day); reply the Reply as a dict (tokens, timings...), None if there is none
MODEL_CALL        = "model.call"          # data: model, system, messages (as sent), tools (the names offered), think, status, error, latency, reply

# A rail of the guard changed a message: the user's before the model reads it, the model's before it is shown,
# or a tool call of the model before it runs (between its TOOL_CALL_STARTED and TOOL_CALL_ENDED).
# A refused message never reaches the model: its turn ends with the reason "refused", and the refusal as message.
# A refused reply is replaced by the refusal, shown and kept in the session in its place.
# A refused call never runs: the refusal is its result, the model reads it and does without
GUARD_TRIGGERED   = "guard.triggered"     # data: stage ("input", "output", "tool_call"), action ("masked", "refused"), rails (the names of those that refused), content (what goes on instead), tool (its name, for "tool_call" only)

# producer: who wanted the call, "model" (the model asked for it), "user" (a command) or "system" (Louis itself)
TOOL_CALL_STARTED = "tool.call.started"   # data: name, arguments (masked with the guard: to show, not to run), producer
TOOL_CALL_ENDED   = "tool.call.ended"     # data: name, producer, ok (False if it did not do it: unknown, crashed, failed or refused), result, duration (seconds)

APP_STARTED       = "app.started"         # data: model (its name), think (True if /think is on), commands: [{name, usage, description}]
APP_STOPPED       = "app.stopped"         # data: reason ("eof", "interrupt")

# A tool asks before acting: the interface shows the request, and answers with the same id.
# Nobody answering means no: without an interface to ask the user, a tool never writes
TOOL_BEGFOR_PERMISSION = "tool.permission.begfor"   # data: id, tool, summary (one sentence), preview (a diff, or "")
TOOL_GRANT_PERMISSION  = "tool.permission.grant"    # data: id, granted

# What the commands tell the user. The data is raw and JSON-friendly (full texts, raw paths): each
# interface lays it out its own way, the CLI as text, a web page as it likes
SESSION_CREATED = "session.created"   # data: user, persistent (saved from the first message of the user on), custom_prompt
SESSION_SAVED   = "session.saved"     # data: id (the current session is in the database, from its first message on)
SESSION_LIST    = "session.list"      # data: user, sessions: [{id, first_message, cwd, here, current, created_at}]
SESSION_RESUMED = "session.resumed"   # data: id, user, messages (count), last_question, last_answer

COMMAND_UNKNOWN = "command.unknown"   # data: name, commands: [{name, usage, description}]
COMMAND_ERROR   = "command.error"     # data: command, reason (a short code), message (one sentence), details...
