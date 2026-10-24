# R2 · RAG avancé

Au-dessus de [R1](R1-rag-basique.md) : les passages trouvés sont relus par un reranker et notés un à un, ceux qui ne répondent pas sont écartés, et le modèle peut filtrer la recherche par métadonnées.

## Ce qu'il fait

- **Reranking** (`rag/reranker.py`) : les 20 passages de l'index (`rag.rerank.pool`) sont relus **avec la question** par un cross-encoder multilingue (`mmarco-mMiniLMv2`, ONNX sur le CPU par `fastembed`). Les meilleurs passent devant.
- **Score par passage** : chaque passage a un score de pertinence de 0 à 1 ; ceux sous `rag.rerank.min_score` (0.05) sont écartés avant d'entrer dans le contexte. Quand tout est écarté, l'outil dit au modèle que la base ne couvre pas le sujet.
- **Filtres** : `search_knowledge(query, source?, path?, kind?, modified_after?)`. `kind` : `code`, `doc`, `config`, `data` ; `path` : un dossier ou un motif (`src/auth`, `docs/*.md`) ; `modified_after` : la date du dernier commit du fichier (`2026-09-30`). Appliqués **avant** le classement.
- **Catalogue** : la description de l'outil liste chaque source, ses genres de fichiers, ses dossiers et sa période : le modèle sait quoi filtrer.
- **Descriptions du code** (`--describe`) : un petit modèle écrit ce que fait chaque passage de code, en une phrase cherchée avec lui.
- **Mesurer** : `python -m rag.evaluate` donne hit@1, hit@4, hit@20 et un tableau des seuils.
- Sans `fastembed` ou son modèle, la recherche continue dans l'ordre de l'index.

## Commandes

| Commande | Comment ça marche | À quoi ça sert |
| -------- | ----------------- | -------------- |
| `cd src && python -m rag.reranker` | télécharge le cross-encoder, une fois | activer le reranking et le seuil |
| `/index <dossier> [<nom>] --describe` | un petit modèle décrit chaque passage de code ; gardé pour la suite, `--no-describe` l'arrête | trouver du code par ce qu'il fait, pas par ses noms |
| `search_knowledge(query, source?, path?, kind?, modified_after?, max_results?)` (outil du modèle) | filtre, cherche, reranke, écarte sous le seuil | des passages ciblés et sûrs |
| `python -m rag.evaluate <questions.json>` | pose les questions sans le chat, donne hit@1/4/20 et un tableau des seuils | mesurer la recherche |
| `… --save f.json` / `--baseline f.json` | garde un run / compare question par question | voir ce qu'un réglage change |
| `… --no-rerank`, `--rerank-model`, `--min-score`, `--max-chars`, `--no-filters`, `-k` | essaie d'autres réglages sans toucher à `settings.py` | choisir un modèle ou un seuil |

## Exemples

```bash
cd src && python -m rag.reranker                         # télécharge le reranker une fois (install.sh le fait)
louis --index ~/projet --name api --describe
cd src && python -m rag.evaluate questions.json --save avant.json   # format des questions : docs/RAG.md
```

```
> Où est géré le login dans l'API, et qu'est-ce qui a changé ce mois-ci ?
  ● Connaissances « login » (api, path=src/auth, kind=code, modified_after=2026-10-01)
    ⎿ 3 passages (2 écartés par le reranker)
```

Détails et mesures : [docs/RAG.md](../../RAG.md). Tests : `tests/test_knowledge.py`, `tests/test_describer.py`, `tests/test_evaluate.py`.
