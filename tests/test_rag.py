##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## The knowledge base, by keywords: what CI can check without Ollama, and that it goes on without it
##
import pytest
from events.event_bus import EventBus
from rag.embedder import Embedder
from rag.index import Index
from rag.knowledge import Knowledge
from tool.impl.rag.tool_knowledge import KnowledgeTool

@pytest.fixture
def docs(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "deploy.md").write_text("# Déploiement\n\nLe serveur de production s'appelle kiwi-prod-7.\n")
    (folder / "team.md").write_text("# Équipe\n\nUne pull request doit être relue par un coéquipier.\n")
    return folder

def knowledge(tmp_path, embedder: Embedder | None = None) -> Knowledge:
    return Knowledge(EventBus(), Index(str(tmp_path / "rag.db")), embedder)

def test_a_folder_is_indexed_and_searched_by_keywords(tmp_path, docs, app):
    base: Knowledge = knowledge(tmp_path)
    counts: dict = base.index(str(docs), "docs")
    assert counts["files"] == 2 and counts["chunks"] >= 2
    app.knowledge = base
    found: str = KnowledgeTool().handle(app, query="serveur de production")
    assert found.startswith("[1] docs /deploy.md") and "kiwi-prod-7" in found

def test_without_ollama_it_says_so_and_goes_on_by_keywords(tmp_path, docs):
    # Nothing listens on port 9: Ollama stopped
    base: Knowledge = knowledge(tmp_path, Embedder("http://127.0.0.1:9", "nomic-embed-text"))
    counts: dict = base.index(str(docs), "docs")
    assert counts["embedded"] == 0 and "Ollama ne répond pas" in counts["warning"]
    # assert [hit.path for hit in base.search("relue coéquipier")][0] == "/team.md"
    found = base.search("relue coéquipier")
    assert found.hits
    assert found.hits[0].path == "/team.md"

def test_an_empty_knowledge_base_tells_the_model_to_ask_for_an_index(tmp_path, app):
    app.knowledge = knowledge(tmp_path)
    assert KnowledgeTool().handle(app, query="anything").startswith("Erreur : la base de connaissances est vide")
