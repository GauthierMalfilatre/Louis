# R1 · RAG de base

Louis cherche dans la documentation et le code que tu lui indexes avant de répondre, avec l'outil `search_knowledge` : la base lui rend les quelques passages utiles, qu'il lit dans son contexte.

## Ce qu'il fait

- **Ingestion** (`rag/ingest.py`) : les fichiers texte d'un dossier ; les dépendances, `.git`, les binaires, les fichiers minifiés, générés, de plus de 1 Mo et les fichiers de clés (`.env`, `*.pem`) sont laissés de côté.
- **Découpage** (`rag/chunker.py`) : des passages d'environ 1 500 caractères, coupés à une ligne vide, avec un recouvrement de 3 lignes. Chaque passage reçoit une ligne qui dit où il est (`class Trainer › def run(self)`, le titre d'une section).
- **Embeddings** (`rag/embedder.py`) : un vecteur par passage avec `nomic-embed-text` d'Ollama.
- **Index** (`rag/index.py`) : un fichier SQLite (`louis.rag.db`, `LOUIS_RAG`), le texte en FTS5 (BM25) et les vecteurs. Une recherche fait les deux et fusionne les classements (RRF).
- **Injection** : `search_knowledge` rend les meilleurs passages (`rag.results`, 4) avec leur source et leurs lignes. Il n'est proposé au modèle que si la base contient quelque chose, et sa description liste ce qu'elle contient.
- **Mise à jour** : ré-indexer ne relit que les fichiers changés et oublie ceux qui ont disparu. Sans `nomic-embed-text`, tout marche par mots-clés seulement.

## Commandes

| Commande | Comment ça marche | À quoi ça sert |
| -------- | ----------------- | -------------- |
| `ollama pull nomic-embed-text` | télécharge le modèle d'embedding, une fois | la recherche par le sens (sinon mots-clés seulement) |
| `louis --index <dossier> [--name <nom>] [--exclude <motif>]` | indexe sans lancer le chat ; Ctrl+C garde ce qui est fait | indexer un gros dossier |
| `/index` | liste les sources : fichiers, passages, modèle, motifs exclus | voir ce que la base contient |
| `/index <dossier> [<nom>]` | indexe ou met à jour le dossier (ne relit que ce qui a changé) ; le modèle peut le chercher tout de suite | ajouter de la doc ou du code |
| `/index … --exclude <motif>` | laisse de côté ces fichiers, et aux `/index` suivants ; `--exclude ""` n'exclut plus rien | écarter les tests, les fichiers générés |
| `/unindex <nom>` | retire les passages de la source (le dossier n'est pas touché) | oublier une source |
| `search_knowledge(query, …)` (outil du modèle) | cherche et rend les meilleurs passages avec leur source | répondre à partir de la base |

## Exemples

```bash
ollama pull nomic-embed-text
louis --index ~/docs/python --name python      # sans lancer le chat
```

```
> /index                                    # les sources indexées
> /index ~/docs/rust rust                   # indexe ou met à jour un dossier
> /index ~/projet api --exclude "tests"     # sans ces fichiers, gardé pour la suite
> /unindex rust
> comment lire un fichier json en python ?
  ● Connaissances « lire fichier json »
    ⎿ 4 passages
```

Détails et mesures : [docs/RAG.md](../../RAG.md). Tests : `tests/test_rag.py`, `tests/test_ingest.py`, `tests/test_index.py`, `tests/test_context.py`.
