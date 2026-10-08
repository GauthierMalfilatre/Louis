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
    "chat.model.name"      : "qwen3.5",
    "chat.model.parameters": "9b",
    "chat.uri"             : "http://localhost:11434",
    "chat.tools.maxdepth"  : 40,
    "chat.think"           : False,
    "chat.keepalive"       : "30m",
    # When the context is full, the oldest exchanges left out of what the model sees are summed up by the chat model
    # itself (what was asked, the files read and changed, what is left to do), in its system prompt: it goes on knowing
    # them. One request each time the cut moves forward (a few seconds on the GPU). False: they are only left out
    "chat.compact.summary" : True,
    # Tokens the model sees at once. 12288 keeps qwen3:8b at ~92% GPU on 8 GB of VRAM:
    # above that it spills onto the CPU, and gets much slower
    "chat.context"         : 24576,
    # Tokens a reply may take at most: the room the context window leaves it (30 % of chat.context, see
    # app/context_window.py), less a margin for its estimate. Past it, a reply that never ends (a model going round
    # in circles) is cut, instead of overflowing the context. 3072 tokens: a file of about 300 lines for write_file
    "chat.predict"         : 3072,
    # How the model picks its words: the settings Qwen gives for precise coding. Without them, Ollama uses those of
    # the model, made for chat (qwen3.5: temperature 1.0, presence_penalty 1.5), with which a third of the edits of
    # the model could not be applied, in replays of a real session. {} keeps those of the model
    "chat.options"         : {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "presence_penalty": 0.0},
    # Database of the sessions, in the working directory, unless LOUIS_DB gives another path:
    # the launcher of install.sh points it at the global one
    "db.file"              : "louis.db",
    # Every call to the model and to the tools, one JSON line each (latency, tokens, errors...), next to the database
    # unless LOUIS_TRACES gives another path. louis --dashboard turns them into metrics
    "monitor.file"         : "louis.traces.jsonl",
    # Where /export writes the sessions, relative to the working directory
    "export.dir"           : "exports",
    # Where the public links of /share point to: the address that reaches the server of louis --web (it serves them),
    # unless LOUIS_SHARE_URL gives another. Empty: the address louis --web listens on (http://localhost:8080 without it)
    "share.base_url"       : "",
    # Structured replies (/json, louis --schema): the folder of the project where its own schemas are looked for
    # first (they win over the ones of louis, in src/structured/schemas), and the replies asked of the model before
    # giving up on one that does not match its schema
    "structured.dir"       : "schemas",
    "structured.attempts"  : 3,
    # Reasoning loop (ReAct, /react): the model says what it knows and what it will do before each action, every step
    # is traced, and with reason.verify it checks its answer before giving it (asked again with what is wrong,
    # reason.attempts times at most). On at the start with reason.enabled; its steps are those of chat.tools.maxdepth
    "reason.enabled"       : False,
    "reason.verify"        : True,
    "reason.attempts"      : 2,
    # Guardrails (NeMo) on the messages of the user and the replies of the model, rules in guard/config.
    # Off by default: it needs requirements-guard.txt, and Python 3.13 at most
    "guard.enabled"        : False,
    # Louis signs the commits it makes with a "Co-authored-by" line: the user stays their author. For GitHub to show
    # Louis on the commits, it must be the noreply address of a GitHub account (Settings > Emails). Empty: no line
    "git.coauthor"         : "Louis <336655023+louis-sensai@users.noreply.github.com>",
    # Code the model runs (run_code) goes in a Docker container: no network, no access to the project, read-only disk,
    # limits on time, memory and processes. The tool is only offered if docker is installed. The images must be pulled
    # by the user (docker pull python:3.13-alpine alpine:latest golang:alpine rust:alpine gcc:latest): the container never
    # reaches the network to get them, nor the libraries a program would want (go, rust, c, c++: standard library only)
    "sandbox.enabled"      : True,
    # Bytes of the output of the code the model sees, for each of stdout and stderr: the rest is cut
    "sandbox.output"       : 4000,
    # What differs from the profile of a language (tool/impl/exec/tool_run.py: python and sh 10 s and 256m, c and c++ 30 s, go and rust
    # a minute and 1g for their build): its image, timeout (seconds) and memory. {"python": {"image": "python:3.12-slim"}}
    "sandbox.languages"    : {},
    # Knowledge base (RAG): the folders the user indexes (/index, louis --index: documentation, examples of code...),
    # that the model looks up with search_knowledge. It needs no library beyond numpy; the meaning of the passages is
    # read by an embedding model of Ollama (ollama pull nomic-embed-text), without it the search is by keywords only.
    # The index is in the working directory, unless LOUIS_RAG gives another path (the launcher of install.sh: the global one)
    "rag.enabled"          : True,
    "rag.file"             : "louis.rag.db",
    "rag.embed.model"      : "nomic-embed-text",
    # nomic-embed-text wants to be told which side of the search a text is; another model may want none
    "rag.embed.query_prefix"   : "search_query: ",
    "rag.embed.document_prefix": "search_document: ",
    "rag.embed.batch"      : 32,
    # The questions embedded on the GPU too: off, on the CPU (a question takes ~30 ms, the same vectors). On a GPU of a few
    # GB, every MB the embedding model leaves is one more for the chat model. The passages of /index always go to the GPU:
    # hundreds at once, ~50 times faster there
    "rag.embed.gpu"        : False,
    # Passages search_knowledge gives back by default
    "rag.results"          : 4,
    # A long file with fewer distinct lines than this share was made by a program (a grid of settings, a dump): it is not
    # indexed, its passages would all look alike and take the places of the others. 0: only those marked "@generated"...
    # To leave out other files of a folder: /index <dossier> [<nom>] --exclude "<motif>" (kept for its next /index)
    "rag.index.generated_ratio": 0.10,
    # Descriptions: for a source indexed with --describe, a model of Ollama writes what each passage of code does, in one
    # sentence of plain words searched with it ("lit les touches du clavier" for code that only says K_LEFT). One
    # request per passage at indexing, kept: a passage that did not change is not described again.
    # model: a small one that fits whole in the GPU writes them several times faster than the chat model (measured on
    # 6 GB: ~1.5s a passage with qwen3:4b-instruct, 8 to 18s with qwen3:8b, of which a part runs on the CPU). It must
    # answer without thinking first: an "instruct" model, not a "thinking" one (qwen3:4b is one). None: the chat model.
    # context: its num_ctx when it is not the chat model (a passage and the outline of its file); predict: the tokens of
    # an answer at most
    "rag.describe.model"   : "qwen3:4b-instruct",
    # The scribe: beside the chat, a small model writes the title and the summary of each session once a reply is done
    # (the sidebar of louis --web, /sessions, /find) and the sentence that welcomes the user to a new session on the web
    # page. On the CPU, in its own thread: it never takes the GPU from the chat model, nor slows a reply. Measured on a
    # laptop CPU, loaded: 1.5 to 4s a request with qwen3:4b-instruct (the same as rag.describe.model: one model for
    # both); qwen3:1.7b is twice as fast, but writes "vous", or "Louis a…", and proposes what makes no sense. It must
    # answer without thinking first: an "instruct" model. "": no scribe
    "scribe.model"         : "qwen3:4b-instruct",
    "scribe.gpu"           : False,
    "scribe.keepalive"     : "30m",
    "scribe.context"       : 4096,
    "rag.describe.context" : 4096,
    "rag.describe.predict" : 80,
    # Reranking: the passages the search found are read again with the question by a cross-encoder (ONNX on the CPU,
    # by fastembed: installed with the guard, or by requirements-rerank.txt), the best first, and those under
    # min_score left out (0 to 1: 0 keeps them all). Download the model once: cd src && python -m rag.reranker
    # Without fastembed or the model, the search goes on in the order of the index. Measured with python -m rag.evaluate
    # (docs/RAG.md): mmarco-mMiniLMv2 reads French, ~2.5s a search on a laptop CPU; jinaai/jina-reranker-v2-base-multilingual
    # ranks a little better, but takes ~10s and 5 GB of memory, under a non-commercial license
    "rag.rerank.enabled"   : True,
    "rag.rerank.model"     : "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
    # Passages of the search the reranker reads: the right one is rarely further down (python -m rag.evaluate: hit@20)
    "rag.rerank.pool"      : 20,
    # Measured: 0.05 kept every right answer of the test, and left most of the questions it cannot answer with nothing
    "rag.rerank.min_score" : 0.05,
    # What it reads of each passage: its time grows with it, and the start of a passage tells what it is about
    "rag.rerank.max_chars" : 1000,

}
