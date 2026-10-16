##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Event list
##
# The thinking mode of the model, switched by /think: it thinks before every reply from then on
THINKING_ENABLED  = "chat.thinking.enabled"    # data: none
THINKING_DISABLED = "chat.thinking.disabled"   # data: none
# The reasoning loop (ReAct), switched by /react: the messages are answered step by step from then on
REASONING_ENABLED  = "chat.reasoning.enabled"    # data: none
REASONING_DISABLED = "chat.reasoning.disabled"   # data: none

# The conversation, as it goes: the app never prints, the interfaces show these their own way
CHAT_TURN_STARTED = "chat.turn.started"   # data: none (the model starts answering a message of the user)
CHAT_TURN_ENDED   = "chat.turn.ended"     # data: reason ("done", "cancelled", "error", "rounds", "loop", "length", "refused", "empty", "invalid"), message (None when done or cancelled)
CHAT_TEXT         = "chat.text"           # data: text (a piece of the reply, as the model writes it)
CHAT_REPLY        = "chat.reply"          # data: content (the whole reply, "" if it only calls tools), tools (their names)
# A reply asked as JSON that matches a schema (/json, louis --schema), before CHAT_TURN_ENDED: its JSON when it
# matches, or why the last one did not (the turn then ends with the reason "invalid")
STRUCTURED_REPLY  = "chat.structured"     # data: schema (its name), valid, data (the JSON, None if not valid), attempts (replies asked), errors ([] if valid)
CHAT_NUDGED       = "chat.nudged"         # data: none (the model announced an action without doing it: it is told to)
# A step of the reasoning loop (/react), once the model replied: what it thought (masked with the guard, as the replies
# are), and the tools it decided to call, their results coming in TOOL_CALL_ENDED. A step that calls none is a draft
# of the answer, checked next with reason.verify. step counts from 1 for each message
REASONING_STEP    = "chat.reasoning.step"   # data: step, thought ("" if the model wrote none), tools (their names, [] for a draft)
# The model checked its draft (reason.verify): ok, or what is wrong with it, for it to answer again (attempt counts
# from 1, reason.attempts + 1 at most: the last answer is checked too, and given whatever its check says). A check the
# model could not give counts as ok: it never holds the answer back
REASONING_CHECK   = "chat.reasoning.check"  # data: attempt, ok, problems ([] if ok, masked with the guard), revise (it is written again; False and not ok: given with its problems)
# How full the context of the model is: measured by Ollama after each reply, estimated when the session changes
CHAT_CONTEXT      = "chat.context"        # data: used, size (tokens), estimated
CHAT_THINKING     = "chat.thinking.text"  # data: text (a piece of what the model thinks before replying, with /think)
# The context filled up: the old tool results were cut down to their first lines (the model may ask for them again),
# and at last the oldest exchanges left out. What is saved of the session stays whole
CHAT_COMPACTED    = "chat.compacted"      # data: results (cut down this time), dropped (messages left out this time), summarized (the chat model summed up what was left out, chat.compact.summary), used, size (tokens)

# One request to the model, however it went: what the monitoring records. status is "ok", "error" (error tells why) or
# "cancelled" (Ctrl+C); latency the seconds of the whole request; system the prompt of the session, without the context
# put after it (the date changes it every day); reply the Reply as a dict (tokens, timings...), None if there is none
# purpose: what the call is for, "reply" (to the user), "structured" (JSON for /json), "check" (of a draft, /react) or "summary"
MODEL_CALL        = "model.call"          # data: model, purpose, system, messages (as sent), tools (the names offered), think, status, error, latency, reply

# A rail of the guard changed a message: the user's before the model reads it, the model's before it is shown,
# a tool call of the model before it runs, or the result of a tool that reads what Louis does not own (the knowledge
# base) before the model reads it (both between the TOOL_CALL_STARTED and TOOL_CALL_ENDED of the call).
# A refused message never reaches the model: its turn ends with the reason "refused", and the refusal as message.
# A refused reply is replaced by the refusal, shown and kept in the session in its place.
# A refused call never runs: the refusal is its result, the model reads it and does without.
# A result is never refused, only masked: the passages that give orders to the model are taken out of it, and
# the sensitive data replaced, the model reads the rest
GUARD_TRIGGERED   = "guard.triggered"     # data: stage ("input", "output", "tool_call", "tool_result"), action ("masked", "refused"), rails (the names of those that refused), content (what goes on instead), tool (its name, for "tool_call" and "tool_result" only)

# producer: who wanted the call, "model" (the model asked for it), "user" (a command) or "system" (Louis itself)
TOOL_CALL_STARTED = "tool.call.started"   # data: name, arguments (masked with the guard: to show, not to run), producer
TOOL_CALL_ENDED   = "tool.call.ended"     # data: name, producer, ok (False if it did not do it: unknown, crashed, failed or refused), result, duration (seconds)

# The knowledge base (RAG): the folders the user indexed (/index, louis --index), and what the model looked up in them.
# Nothing is embedded when the embedding model does not answer: the sources are still searched by keywords
RAG_INDEXING       = "rag.indexing"         # data: source, root, files (found in the folder)
RAG_INDEX_PROGRESS = "rag.index.progress"   # data: source, done, total (files)
# A file of a source with --describe: the chat model wrote what its passages do (seconds: of the model, so far)
RAG_DESCRIBE_PROGRESS = "rag.describe.progress"   # data: source, path, described (so far, by the model), reused (so far, from the cache), seconds
RAG_INDEXED        = "rag.indexed"          # data: source, root, files, updated, unchanged, removed, skipped, excluded (by the patterns), exclude (the patterns of the source), generated: [{path, reason}] (made by a program, left out), history (the dates come from git, else from the disk), chunks (added), embedded (of them), warning (why the rest was not embedded, or None), describe (its code is described), described (passages, by the model), reused (descriptions from the cache), describe_warning (why the rest was not described, or None), describe_seconds, duration
RAG_SOURCES        = "rag.sources"          # data: sources: [{name, root, files, chunks, embedded, model, updated_at, exclude (its patterns), describe}]
RAG_FORGOTTEN      = "rag.forgotten"        # data: source, chunks (removed)
# A look-up: the index found candidates, the reranker (when it could) read them again, ranked them by its score (0 to 1)
# and dropped those under its threshold. Without it, score is the fusion of the index and nothing is dropped
RAG_RETRIEVED      = "rag.retrieved"        # data: query, source (None: all), path, kind and after (the filters on the files, None: none; after: "2026-09-30"), files (how many the filters kept, None without them), mode ("hybrid": keywords and meaning, "keyword"), reranker (its model, None if it did not rerank), candidates (found by the index), dropped (under the threshold), hits: [{source, path, start, end, score, fused (the score of the index, None if not reranked)}], rerank (seconds, None), duration (seconds, all of it)

# The semantic cache (cache/): a question close enough in meaning to one already answered gets its answer back without
# the model, or by the seed (answers written by the team, cache/seed/). Looked up before the input rails of the guard
# (its answers went through the output rails when they were kept) and the model: a hit is told by CACHE_HIT, with no
# GUARD_TRIGGERED nor MODEL_CALL in its turn, then its turn goes on as any reply does (CHAT_TEXT, CHAT_REPLY,
# CHAT_TURN_ENDED "done"). Only the answers safe to give again are stored, once their turn is done (cache/rules.py):
# CACHE_STORED
# CACHE_LOOKUP: each message the cache was asked about. reason tells why it was not looked up ("followup": it leans on
# what was said before, "timely": it depends on the time, "project": on the project as it is now, "embed": the embedding
# model does not answer), None if it was
CACHE_LOOKUP   = "cache.lookup"     # data: hit, score (the closest entry, None without one), duration (seconds), reason
CACHE_HIT      = "cache.hit"        # data: id, score (closeness in meaning, 0 to 1), verified (the reranker: they ask the same, 0 to 1, None if not checked), question (the one answered before), age (seconds), hits (served, this one included), seed (written by the team)
CACHE_STORED   = "cache.stored"     # data: id, tools (the ones the answer used)
CACHE_ENABLED  = "cache.enabled"    # data: none
CACHE_DISABLED = "cache.disabled"   # data: none
# Entries removed: "all" (/cache clear, those of the user), "last" (/cache forget, the answer served last), "rag" (the
# knowledge base changed: the answers that looked it up)
CACHE_CLEARED  = "cache.cleared"    # data: scope, entries (removed)
CACHE_STATS    = "cache.stats"      # data: enabled, entries (answers of the model), seeds (questions of the seed), shared (by the users), hits (served, ever), lookups and served (this run), hit_rate (this run, None before any lookup), threshold, file

APP_STARTED       = "app.started"        # data: model (its name), think (True if /think is on), react (True if /react is on), commands: [{name, usage, description}]

# The judge (eval/): an answer of Louis read again by a model, after its turn, against the sources its tools read.
# claims: [{text, verdict ("supported", "contradicted", "unverifiable"), source (its number from 1, 0: none), evidence
# (the passage quoted, "" none), quoted (the quote is really in the source), reason}]. faithfulness is the share of the
# claims supported, None when the answer read no source or holds no fact; relevance and coherence go from 1 to 5.
# EVAL_SCORED is told once per judgment, from the thread of the judge when it runs in the background: only the
# monitoring and the log listen to it. EVAL_REPORT is what /eval shows, from the thread of the app: the interfaces
# EVAL_STARTED: the judge starts on an answer (from its thread too), until its EVAL_SCORED: the interfaces may show it works
EVAL_STARTED      = "eval.started"        # data: id (of the answer, as EVAL_SCORED names it)
EVAL_SCORED       = "eval.scored"         # data: id, session, model, prompt (its version), question, answer, sources: [{tool, arguments, chars}], judge (its model), status ("ok", "error"), error, faithfulness, relevance, relevance_reason, coherence, coherence_reason, claims, duration (seconds)
EVAL_REPORT       = "eval.report"         # data: the same as EVAL_SCORED

APP_STOPPED       = "app.stopped"         # data: reason ("eof", "interrupt")

# A tool asks before acting: the interface shows the request, and answers with the same id.
# Nobody answering means no: without an interface to ask the user, a tool never writes
# every_time: never granted by an "always" given before, the user is asked again (a share makes a link public)
TOOL_BEGFOR_PERMISSION = "tool.permission.begfor"   # data: id, tool, summary (one sentence), preview (a diff, or ""), every_time
TOOL_GRANT_PERMISSION  = "tool.permission.grant"    # data: id, granted

# What the commands tell the user. The data is raw and JSON-friendly (full texts, raw paths): each
# interface lays it out its own way, the CLI as text, a web page as it likes
SESSION_CREATED = "session.created"   # data: user, persistent (saved from the first message of the user on), custom_prompt
SESSION_SAVED   = "session.saved"     # data: id (the current session is in the database, from its first message on)
SESSION_LIST    = "session.list"      # data: user, sessions: [{id, first_message, title, summary (the scribe's, None before), cwd, here, current, created_at}]
# Sessions found by /find: by the meaning of their title and summary when the embedding model answers, else by words.
# score: how close (0 to 1, meaning; the share of the words found, words)
SESSION_FOUND   = "session.found"     # data: user, query, mode ("meaning" or "words"), sessions: [{id, title, summary, first_message, cwd, here, current, created_at, score}]
SESSION_RESUMED = "session.resumed"   # data: id, user, messages (count), last_question, last_answer, history (the conversation, as export/document.py reads it)

# A session written to a file by /export: id is None for a session never saved (the anonymous user's). With
# --artifact, files the model wrote alone: files are their paths (None for a whole session)
EXPORT_DONE     = "export.done"       # data: format ("json"...), path (absolute), id, messages (count, as exported), files, artifacts (count of files)

# Public links (/share, /shares, /unshare): a share is the document as it was then, its sensitive data masked
SHARE_CREATED   = "share.created"     # data: token, url, kind ("session" or "artifact"), id (the session), title, masked (texts changed)
SHARE_LIST      = "share.list"        # data: user, shares: [{token, url, kind, session_id, title, created_at}] (newest first)
SHARE_REVOKED   = "share.revoked"     # data: token, url

SCHEMA_LIST     = "schema.list"       # data: folder (the one of the project), schemas: [{name, description, origin ("projet" or "louis"), path, ok}]

# What the scribe wrote (session/scribe.py). Dispatched from its own thread, a reply never waits for it: a handler of
# these must be thread-safe, and never draw in a terminal
SESSION_DESCRIBED = "session.described"   # data: id, title, summary
APP_WELCOME       = "app.welcome"         # data: lead (one sentence that welcomes the user to the new session, from the last one and the changes of the project)

COMMAND_UNKNOWN = "command.unknown"   # data: name, commands: [{name, usage, description}]
COMMAND_ERROR   = "command.error"     # data: command, reason (a short code), message (one sentence), details...
