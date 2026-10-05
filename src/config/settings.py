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
    # Every call to the model and to the tools, one JSON line each (latency, tokens, errors...), next to the database
    # unless LOUIS_TRACES gives another path. louis --dashboard turns them into metrics
    "monitor.file"         : "louis.traces.jsonl",
    # Guardrails (NeMo) on the messages of the user and the replies of the model, rules in guard/config.
    # Off by default: it needs requirements-guard.txt, and Python 3.13 at most
    "guard.enabled"        : True,
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
