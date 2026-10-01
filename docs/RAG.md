# Base de connaissances (RAG)

Louis peut chercher dans de la documentation et des exemples de code que tu lui indexes, avant d'écrire du code qui s'en sert. Le modèle (qwen3:8b, 12 288 tokens de contexte) ne connaît pas toutes les bibliothèques, et ne peut pas lire des gigaoctets : la base lui rend les quelques passages utiles.

## Utilisation

```bash
ollama pull nomic-embed-text            # une fois : le modèle qui lit le sens des passages (274 Mo)

louis --index ~/docs/python --name python   # indexe un gros dossier, sans lancer le chat (Ctrl+C : ce qui est fait est gardé)
louis                                       # puis, dans une session :
> /index                                    # les sources indexées
> /index ~/docs/rust rust                   # indexe (ou met à jour) un dossier, sous le nom « rust »
> /unindex rust                             # retire une source
> comment lire un fichier json en python ?  # Louis appelle search_knowledge tout seul
```

- Ré-indexer un dossier ne relit que les fichiers qui ont changé, et oublie ceux qui ont disparu.
- `search_knowledge` n'est proposé au modèle que si la base contient quelque chose (un outil de plus, c'est du contexte de moins).
- Sans `nomic-embed-text` (ou si Ollama est arrêté), l'indexation et la recherche continuent **par mots-clés seulement** ; relancer `/index` ajoute ensuite les vecteurs manquants.
- Les passages trouvés sont relus par un **reranker**, qui met le meilleur devant et écarte ceux qui ne répondent pas (voir [Reranking](#reranking)) : `install.sh` l'installe ; sans lui, la recherche marche toujours.
- Les réglages sont dans `src/config/settings.py` (`rag.*`). Changer `rag.embed.model` est possible : les vecteurs de chaque source sont refaits à sa prochaine indexation. Un autre modèle veut peut-être d'autres préfixes (`rag.embed.query_prefix` et `document_prefix`).
- L'index est un fichier SQLite : `louis.rag.db` dans le dossier courant, ou `~/.local/share/louis/louis.rag.db` avec le lanceur de `install.sh` (`LOUIS_RAG` change le chemin). La documentation n'est pas propre à un projet : c'est pour ça que le lanceur le met à part.

## Comment c'est fait

| Étape | Où | Ce qui se passe |
| ----- | -- | --------------- |
| Choix des fichiers | `rag/ingest.py` | Les dossiers de dépendances et `.git`, les liens, les fichiers binaires, minifiés ou de plus de 1 Mo, les lockfiles et les fichiers de clés (`.env`, `*.pem`...) sont laissés de côté |
| Découpage | `rag/chunker.py` | Des passages d'environ 1 500 caractères, coupés à une ligne vide quand il y en a une, avec 3 lignes de recouvrement |
| Sens | `rag/embedder.py` | Un vecteur par passage, par un modèle d'embedding d'Ollama (`/api/embed`) |
| Index | `rag/index.py` | SQLite : le texte en FTS5 (BM25) et les vecteurs en blob. Une recherche fait les deux et fusionne les classements (reciprocal rank fusion) : les mots-clés trouvent le nom exact d'une fonction, les vecteurs trouvent ce que la question veut dire sans ses mots |
| Reranking | `rag/reranker.py` | Les 20 passages trouvés sont relus **avec la question** par un cross-encoder, qui note de 0 à 1 à quel point chacun y répond : les meilleurs passent devant, ceux sous `rag.rerank.min_score` sont écartés |
| Façade | `rag/knowledge.py` | `Knowledge.index()` et `Knowledge.search()` : ce sont les seuls points d'entrée |
| Outil | `tool/impl/rag/tool_knowledge.py` | `search_knowledge(query, source?, max_results?)` : un outil comme les autres, enregistré dans le `ToolManager` |

Tout passe par le bus d'événements, comme le reste de Louis (`events/event_list.py`) : `RAG_INDEXING`, `RAG_INDEX_PROGRESS`, `RAG_INDEXED`, `RAG_SOURCES`, `RAG_FORGOTTEN`, `RAG_RETRIEVED`. Les interfaces les affichent à leur façon (le CLI en texte), le moniteur enregistre chaque recherche (ligne `rag` de `louis.traces.jsonl`) : avec le reranker, ses scores et ceux de la fusion (`fused`), les passages écartés (`dropped`) et son temps (`rerank`).

## Reranking

La fusion (RRF) ne donne qu'un **rang** : son score dit dans combien de listes un passage est arrivé, pas s'il répond. On ne peut ni s'y fier pour l'ordre fin, ni y mettre un seuil. Le cross-encoder lit la question et un passage ensemble (le chemin compris : « AgentPPO/model.py » dit de quoi parle le passage) et donne un score de pertinence. Il lit chaque paire, donc seulement les 20 passages que l'index a trouvés.

- Quand le reranker a tout écarté, `search_knowledge` le dit au modèle autrement que « aucun résultat » : la base ne couvre pas le sujet, chercher avec d'autres mots ne servirait à rien.
- Il tourne en ONNX sur le CPU (`fastembed`, sans torch) : le GPU est au modèle de chat. `fastembed` vient avec le garde-fou, sinon `pip install -r requirements-rerank.txt`. Le modèle se télécharge une fois (`install.sh` le fait) : `cd src && python -m rag.reranker`. Louis ne le télécharge jamais pendant une conversation.
- Sans `fastembed` ou sans le modèle, la recherche continue dans l'ordre de l'index, rien n'est écarté (un avertissement dans `louis.log`).

Le garde-fou passe **après** : il relit le résultat final, déjà trié et réduit. Un passage piégé qui se ferait bien noter (« ceci est la réponse à toute question sur... ») est donc toujours retiré, au prix d'une place parmi les 4.

## Mesurer

`cd src && python -m rag.evaluate ../docs/rag_eval.json` pose les questions du fichier (chacune avec les passages qui y répondent, ou aucun pour une question hors sujet) sans le modèle de chat, et donne hit@1, hit@4, hit@20 et un tableau des seuils. `--save` puis `--baseline` comparent deux réglages question par question ; `--no-rerank`, `--rerank-model`, `--min-score` et `--max-chars` en essaient d'autres sans toucher aux réglages.

Mesures sur un projet de 34 fichiers (835 passages, 22 questions avec réponse et 6 hors sujet, i5-10500H sans GPU) :

| | hit@1 | hit@4 | Hors sujet sans aucun passage | Temps d'une recherche | Mémoire |
| - | - | - | - | - | - |
| Index seul (RRF) | 0.50 | 0.55 | 0 / 6 | – | – |
| `jinaai/jina-reranker-v2-base-multilingual` (seuil 0.3) | 0.68 | 0.77 | 5 / 6 | ~10,6 s | 5,3 Go |
| `Xenova/ms-marco-MiniLM-L-6-v2` (anglais) | 0.45 | 0.64 | inutilisable : il note le français près de 0 | ~1,9 s | |
| **`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, 1 000 caractères, seuil 0.05** (défaut) | **0.64** | **0.77** | **5 / 6** | **~2,6 s** | ~2,8 Go |

- Le temps d'un cross-encoder croît avec ce qu'il lit : couper chaque passage à 1 000 caractères a fait gagner un tiers du temps sans rien perdre (le début d'un passage dit de quoi il parle). À 600, la réponse était trop souvent coupée (hit@4 0.68). Le nombre de threads n'a rien changé, la version quantifiée en 8 bits non plus (et elle range moins bien).
- hit@20 (0.86) est le plafond du reranker : il ne peut que réordonner ce que l'index lui donne. Les 3 questions manquées par l'index le restent (une question en français sur du code qui dit `fuel`, « maximum » face à `MAX_FUEL`, un fichier généré de 600 passages qui prend les places des mots-clés).
- Le seuil a été choisi sur ces 28 questions : avec d'autres sources, mesure à nouveau avant de le monter (au-dessus de 0.1, de bonnes réponses commencent à être écartées).

## Garde-fou

Ce que la base rend est écrit par d'autres : c'est de la donnée, jamais des ordres. Avec `guard.enabled`, le résultat de `search_knowledge` passe par les rails `tool_input` de NeMo (`guard/config/config.yml`, liste `custom_data.guard.untrusted_tools`) avant que le modèle le lise :

- `drop injected passages in tool results` retire les passages qui lui donnent des ordres (« ignore tes instructions... », en français ou en anglais) et les remplace par une ligne qui le dit. Un passage piégé ne coûte pas les autres au modèle ;
- `mask sensitive data in tool results` masque les secrets, e-mails, IBAN, cartes et numéros français que le dossier indexé contenait.

Les fichiers du projet (`cat_file`...) restent hors de cette liste : masquer un fichier que le modèle s'apprête à modifier ferait que son `old_string` ne correspond plus. Sans garde-fou, rien n'est filtré : n'indexe que des sources en qui tu as confiance.

## Où trouver plus de données

Pour un assistant de code, **la qualité compte plus que le volume** : quatre passages de 1 500 caractères sont tout ce que le modèle lit à chaque recherche. Commence par la documentation des langages que l'équipe utilise (quelques centaines de Mo au plus), mesure avec une vingtaine de vraies questions, puis élargis.

*Ces sources sont celles que je connais ; les tailles sont approximatives et je n'ai pas revérifié les adresses ni les licences aujourd'hui : regarde la licence de chacune avant de l'indexer, et surtout avant de redistribuer quoi que ce soit.*

**1. La documentation officielle** (la meilleure valeur : structurée, à jour, avec des exemples). Cherche le dépôt Git de la doc, en Markdown ou reStructuredText de préférence :

| Source | À indexer | Licence |
| ------ | --------- | ------- |
| Python | `Doc/` du dépôt `python/cpython` | PSF |
| Django | `docs/` du dépôt `django/django` | BSD |
| Node.js | `doc/api/` du dépôt `nodejs/node` | MIT |
| Web (HTML, CSS, JS) | `files/en-us/` du dépôt `mdn/content` | CC-BY-SA (le texte), CC0 (les exemples) |
| Rust | le dépôt `rust-lang/book` | MIT / Apache-2.0 |
| Git | `Documentation/` du dépôt `git/git` | GPL-2.0 |

```bash
git clone --depth 1 https://github.com/python/cpython ~/docs/cpython
louis --index ~/docs/cpython/Doc --name python
```

Le C et le C++ (les projets Epitech) : les pages de manuel Linux (dépôt `mkerrisk/man-pages`) et cppreference (archive hors ligne). Ces deux-là ne sont pas en Markdown (roff, HTML) : convertis-les en texte d'abord (`pandoc`, `html2text`), l'indexeur ne retire pas les balises et elles polluent les vecteurs.

**2. Des exemples de code à grande échelle**

| Jeu de données | Contenu | Pour quoi faire |
| -------------- | ------- | --------------- |
| **CodeSearchNet** | environ 2 millions de paires (commentaire, fonction) en 6 langages (Python, JavaScript, Ruby, Go, Java, PHP), tirées de GitHub | Retrouver une fonction à partir d'une phrase : c'est exactement la forme d'une question à Louis. Exporte chaque fonction dans un fichier (ou un `.md` par fonction avec son commentaire) avant de l'indexer |
| **Stack Overflow** (les *data dumps* de Stack Exchange, sur archive.org) | Questions et réponses, CC-BY-SA : garde l'attribution | Les questions pratiques (« comment... », les erreurs). Filtre : réponse acceptée, score ≥ 5, tags de tes langages, sinon c'est du bruit |
| **The Stack** (`bigcode/the-stack-v2`, `bigcode/the-stack-smol` sur Hugging Face) | Du code GitHub sous licences permissives, en téraoctets ; *smol* en est un échantillon de quelques milliers de fichiers par langage | Trop gros pour cette base tel quel. Prends *smol* pour essayer, ou un seul langage filtré ; il faut accepter les conditions d'accès sur Hugging Face |
| **Ton propre code** | `louis --index . --name projet`, ou les dépôts de l'équipe | La recherche par le sens dans un gros dépôt, là où `search` (une regex) ne trouve que les mots exacts |

HumanEval et MBPP sont des jeux d'évaluation (quelques centaines de problèmes) : utiles pour mesurer un modèle, pas à indexer.

**Ce que cette base ne fait pas (encore)** : elle compare tous les vecteurs en mémoire (numpy), à l'aise jusqu'à 100 000 à 200 000 passages (300 à 600 Mo de RAM avec `nomic-embed-text`). Au-delà, il faudra un vrai index de vecteurs (`sqlite-vec`, FAISS, Qdrant) : seul `rag/index.py` change, `Knowledge` et l'outil n'en savent rien.
