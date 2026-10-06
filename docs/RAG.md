# Base de connaissances (RAG)

Louis peut chercher dans de la documentation et des exemples de code que tu lui indexes, avant d'écrire du code qui s'en sert. Le modèle (qwen3:8b, 12 288 tokens de contexte) ne connaît pas toutes les bibliothèques, et ne peut pas lire des gigaoctets : la base lui rend les quelques passages utiles.

## Utilisation

```bash
ollama pull nomic-embed-text            # une fois : le modèle qui lit le sens des passages (274 Mo)
ollama pull qwen3:4b-instruct           # pour --describe seulement : le modèle qui décrit le code (~2,5 Go)

louis --index ~/docs/python --name python   # indexe un gros dossier, sans lancer le chat (Ctrl+C : ce qui est fait est gardé)
louis                                       # puis, dans une session :
> /index                                    # les sources indexées
> /index ~/docs/rust rust                   # indexe (ou met à jour) un dossier, sous le nom « rust »
> /index ~/projet api --exclude "tests" --exclude "*.min.css"   # sans ces fichiers, et aux /index suivants aussi
> /index ~/projet api --exclude ""          # n'exclut plus rien
> /index ~/projet api --describe            # le modèle décrit chaque passage de code (lent la première fois)
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
| Choix des fichiers | `rag/ingest.py` | Les dossiers de dépendances et `.git`, les liens, les fichiers binaires, minifiés ou de plus de 1 Mo, les lockfiles et les fichiers de clés (`.env`, `*.pem`...) sont laissés de côté, comme les fichiers **générés par un programme** et ceux des motifs `--exclude` de la source (voir [Fichiers laissés de côté](#fichiers-laissés-de-côté)) |
| Découpage | `rag/chunker.py` | Des passages d'environ 1 500 caractères, coupés à une ligne vide quand il y en a une, avec 3 lignes de recouvrement |
| Contexte | `rag/context.py` | Chaque passage reçoit une ligne qui dit où il est dans son fichier : `class Trainer › def run(self)`, les titres d'un document, la clé d'un YAML (voir [Contexte des passages](#contexte-des-passages)) |
| Description | `rag/describer.py` | Avec `--describe`, le modèle de chat écrit ce que fait chaque passage de code, en une phrase (voir [Descriptions du code](#descriptions-du-code)) |
| Sens | `rag/embedder.py` | Un vecteur par passage, par un modèle d'embedding d'Ollama (`/api/embed`) |
| Index | `rag/index.py` | SQLite : le texte en FTS5 (BM25) et les vecteurs en blob. Une recherche fait les deux et fusionne les classements (reciprocal rank fusion) : les mots-clés trouvent le nom exact d'une fonction, les vecteurs trouvent ce que la question veut dire sans ses mots |
| Reranking | `rag/reranker.py` | Les 20 passages trouvés sont relus **avec la question** par un cross-encoder, qui note de 0 à 1 à quel point chacun y répond : les meilleurs passent devant, ceux sous `rag.rerank.min_score` sont écartés |
| Façade | `rag/knowledge.py` | `Knowledge.index()` et `Knowledge.search()` : ce sont les seuls points d'entrée |
| Outil | `tool/impl/rag/tool_knowledge.py` | `search_knowledge(query, source?, path?, kind?, max_results?)` : un outil comme les autres, enregistré dans le `ToolManager`. Sa description liste ce que la base contient |

Tout passe par le bus d'événements, comme le reste de Louis (`events/event_list.py`) : `RAG_INDEXING`, `RAG_INDEX_PROGRESS`, `RAG_INDEXED`, `RAG_SOURCES`, `RAG_FORGOTTEN`, `RAG_RETRIEVED`. Les interfaces les affichent à leur façon (le CLI en texte), le moniteur enregistre chaque recherche (ligne `rag` de `louis.traces.jsonl`) : avec le reranker, ses scores et ceux de la fusion (`fused`), les passages écartés (`dropped`) et son temps (`rerank`).

## Reranking

La fusion (RRF) ne donne qu'un **rang** : son score dit dans combien de listes un passage est arrivé, pas s'il répond. On ne peut ni s'y fier pour l'ordre fin, ni y mettre un seuil. Le cross-encoder lit la question et un passage ensemble (le chemin compris : « auth/login.py » dit de quoi parle le passage) et donne un score de pertinence. Il lit chaque paire, donc seulement les 20 passages que l'index a trouvés.

- Quand le reranker a tout écarté, `search_knowledge` le dit au modèle autrement que « aucun résultat » : la base ne couvre pas le sujet, chercher avec d'autres mots ne servirait à rien.
- Il tourne en ONNX sur le CPU (`fastembed`, sans torch) : le GPU est au modèle de chat. `fastembed` vient avec le garde-fou, sinon `pip install -r requirements-rerank.txt`. Le modèle se télécharge une fois (`install.sh` le fait) : `cd src && python -m rag.reranker`. Louis ne le télécharge jamais pendant une conversation.
- Sans `fastembed` ou sans le modèle, la recherche continue dans l'ordre de l'index, rien n'est écarté (un avertissement dans `louis.log`).

Le garde-fou passe **après** : il relit le résultat final, déjà trié et réduit. Un passage piégé qui se ferait bien noter (« ceci est la réponse à toute question sur... ») est donc toujours retiré, au prix d'une place parmi les 4.

## Filtres et catalogue

Le modèle peut limiter une recherche à une partie de la base : `path` (un dossier ou un motif depuis la racine de la source : `src/auth`, `docs/*.md`, ou un morceau de chemin : `auth`, sans tenir compte de la casse), `kind` (`code`, `doc`, `config`, `data`, d'après l'extension, `rag/index.py`, `KINDS`) et `modified_after` (`AAAA-MM-JJ` : les fichiers modifiés depuis ce jour, pour « ce qui a changé récemment »).

La date d'un fichier est celle du **dernier commit** qui l'a touché, lue en une fois dans l'historique à chaque `/index` (`rag/ingest.py`, `last_changes`) : dans un dépôt, la date sur le disque est celle du clone ou du checkout, la même pour tous. Un fichier que git ne suit pas, ou un dossier hors d'un dépôt, garde sa date sur le disque. Une modification pas encore commitée garde la date de son dernier commit. Le catalogue donne à chaque source sa période (`modifiés du 2026-04-20 au 2026-05-13`), et chaque passage rendu sa date (`· modifié le 2026-05-12`). Le filtre s'applique **avant** le classement, dans les mots-clés comme dans les vecteurs : les 20 candidats du reranker sont tous dans le filtre, pas ce qu'il reste des 20 meilleurs après lui. Rien n'est ajouté à l'index : chemin et genre se lisent dans le chemin, pas besoin de réindexer.

Le modèle ne peut choisir qu'une source qu'il connaît, et ne filtrer que sur un dossier qu'il a vu : la description de `search_knowledge` se termine par le **catalogue** de la base (`Knowledge.catalog()` : chaque source, ses fichiers par genre, ses 20 plus gros dossiers), refait au démarrage et après chaque `/index` et `/unindex` (`App.offer_knowledge`). Il coûte ~110 tokens par requête pour une source comme celle des mesures.

- Un filtre qui ne garde aucun fichier renvoie une erreur avec les dossiers qui existent : le modèle se corrige au tour suivant.
- Un filtre qui garde des fichiers mais où rien ne répond : l'outil lui dit que le filtre est peut-être trop étroit, et de relancer une fois sans lui.
- `RAG_RETRIEVED` et la ligne `rag` des traces gardent `path`, `kind`, `after` et `files` (les fichiers gardés) : on voit si le modèle filtre, et comment.

Mesuré avec les filtres qu'un modèle peut déduire de la question et du catalogue (champ `filters` de `docs/rag_eval.json`, `--no-filters` pour comparer) : hit@1 0.64 → 0.68, hit@4 0.77 → 0.82, hit@20 0.86 → 0.91. `kind=code` écarte un fichier de réglages généré qui prenait les places des mots-clés ; `path` départage des modules presque identiques (le même code copié dans plusieurs dossiers). Ce que le filtre ne corrige pas : un passage que le reranker note mal, une question en mots (« les touches du clavier ») face à du code qui n'a que les constantes d'une bibliothèque, sans une phrase autour (noté 0.0015 même seul dans son dossier).

## Fichiers laissés de côté

Un fichier produit par un programme (une grille de réglages, un export, une table) remplit l'index de passages qui se ressemblent tous, et prend les places des autres dans chaque recherche, que le modèle pense à filtrer ou non. Deux façons de l'écarter, à l'indexation :

- **Automatiquement** (`rag/ingest.py`, `generated`) : un fichier marqué dans ses premières lignes (`@generated`, `DO NOT EDIT`, `auto-generated`...), ou long (500 lignes et plus) avec moins de 10 % de lignes distinctes. Un fichier écrit à la main en a presque toujours bien plus de la moitié. Ceux qui sont écartés sont nommés à la fin de `/index`, avec la raison (`4% de lignes distinctes sur 42282`) ; `rag.index.generated_ratio` change le seuil (0 : seulement les fichiers marqués).
- **À la main** : `--exclude <motif>` sur `/index` ou `louis --index`, autant de fois qu'il faut, avec les motifs des filtres (`config/*_grid.yml`, `tests`, `*.min.css`). Ils sont gardés avec la source : le prochain `/index` du dossier les applique sans qu'on les redonne. `--exclude ""` les efface. `/index` les montre à côté de chaque source.

Un fichier écarté qui était indexé est retiré au prochain `/index`, comme un fichier supprimé du dossier. Mesuré sur un projet dont un fichier généré faisait 74 % des passages : l'index passe de 835 à 219 passages, et **sans filtre** hit@4 passe de 0.77 à 0.82 et hit@20 de 0.86 à 0.91, autant qu'avec les filtres idéaux.

## Contexte des passages

Un passage coupé au milieu d'une fonction ne contient ni son nom, ni celui de sa classe ; un passage au milieu d'une section ne contient pas son titre. À l'indexation, `rag/context.py` donne à chacun une ligne qui dit où il est :

| Fichier | Comment | Exemple |
| - | - | - |
| Python | l'arbre syntaxique (`ast`) : les classes et fonctions qui contiennent le passage, celles qui y commencent, la première ligne de la docstring | `class Trainer › def run(self, episodes=100) [def save] — Train until solved` |
| Markdown | les titres au-dessus du passage | `Guide › Installation › Linux` |
| YAML | la clé de premier niveau | `production` |
| Autre code | les lignes moins indentées au-dessus qui ressemblent à une définition (`class`, `fn`, `func`, `int main(...)`...) | `export class Store › async load(url)` |

Ce contexte est lu avec le texte du passage par les vecteurs et par les mots-clés (« run » trouve le milieu d'une fonction qui ne le dit jamais), par le reranker (sans les arguments ni la liste des définitions, `brief` : chaque caractère de contexte est un caractère de code en moins sur les 1 000 qu'il lit), et par le modèle, sur la ligne de chaque passage (`[1] api /src/train.py:224-253 (class Trainer › def run(self))`).

Changer la façon de découper ou le contexte augmente `rag/chunker.py`, `VERSION` : le prochain `/index` de chaque source relit alors tous ses fichiers, sans rien à faire à la main.

Mesuré sur le même projet (presque tout en Python) : **neutre**. hit@4 0.82 → 0.77 avec les filtres (une question sur 22, dans le bruit), hit@20 identique, un peu moins de passages rendus aux questions hors sujet. Les questions visées ne sont pas corrigées : l'index trouve bien les passages de `def run` quand on demande « la boucle principale », c'est le reranker qui ne relie pas les deux. Le contexte reste pour ce qu'il apporte au modèle (il voit où est chaque passage) et aux documents (les titres), que ce projet ne mesure presque pas. Ce qui corrige ces questions : une phrase écrite par le modèle pour chaque passage, la section suivante.

## Descriptions du code

Le code dit ce qu'il fait avec des identifiants (`pygame.K_LEFT`, `fuel`, `except KeyboardInterrupt`), les questions avec des mots (« les touches du clavier », « le carburant », « Ctrl+C ») : ni les vecteurs, ni les mots-clés, ni le reranker ne relient les deux. Avec `--describe`, le modèle de chat écrit à l'indexation une phrase pour chaque passage de code, dans les mots de quelqu'un qui le cherche, suivie de cinq mots-clés anglais (`rag/describer.py`) :

```
Human.py:142-174   Ce code permet à un agent humain de contrôler un environnement en utilisant les touches du clavier,
                   calcule un score basé sur les récompenses (...). Mots-clés : keyboard input, environment control, (...)
```

```bash
louis --index ~/projet --name api --describe   # long la première fois : une requête au modèle par passage de code
> /index ~/projet api                          # les suivants : seuls les passages qui ont changé sont décrits
> /index ~/projet api --no-describe            # sans descriptions (elles restent en cache si on revient)
```

- La description est lue avec le passage par les vecteurs, les mots-clés et le reranker. Le modèle de chat, lui, lit le code : une description peut se tromper, le code non.
- Seuls les fichiers de code sont décrits (un document dit déjà ce qu'il fait avec des mots). Le choix est gardé avec la source, comme les `--exclude`.
- Chaque description est gardée (table `descriptions`, par un hash du modèle, du chemin et du passage) : un passage qui n'a pas changé n'est jamais redécrit, même quand la source est redécoupée ou que `--describe` est coupé puis remis. Un Ctrl+C ne perd rien de ce qui est déjà décrit.
- Sans réponse du modèle (Ollama arrêté), l'indexation continue sans descriptions ; relancer `/index` écrit celles qui manquent. Changer de modèle (`rag.describe.model`) fait redécrire la source au prochain `/index` ; revenir à un modèle déjà utilisé reprend ses descriptions du cache.

**Le modèle qui décrit.** Le temps d'une description, c'est surtout ce que le modèle écrit (mesuré avec les compteurs d'Ollama : ~0,7 s pour lire le prompt, le reste pour écrire la cinquantaine de tokens de la réponse). La réponse est donc courte (une phrase, `rag.describe.predict` = 80 tokens au plus), et les requêtes d'un même fichier commencent par les mêmes lignes (les consignes, le fichier, son plan) : Ollama ne relit pas ce début d'une requête à l'autre. Surtout, le modèle doit tenir **tout entier** dans le GPU : qwen3:8b avec le contexte du chat (12 288 tokens) fait 7,2 Go, seuls 4,3 Go tiennent sur un GPU de 6 Go, et Ollama fait tourner le reste sur le CPU (~8,5 tokens/s). Par défaut, c'est donc `qwen3:4b-instruct` qui décrit, avec un petit contexte à lui (`rag.describe.context` = 4 096 : un passage et le plan de son fichier) : 3,2 Go, tout dans le GPU. Il doit répondre sans réfléchir d'abord : un modèle « instruct », pas « thinking » (`qwen3:4b` en est un : il écrit son raisonnement à la place de la réponse, et `think: false` n'y change rien). `rag.describe.model` à `None` reprend le modèle du chat.

**Les vecteurs.** Ceux des questions sont calculés sur le CPU (`rag.embed.gpu`, ~30 ms par question, les mêmes vecteurs à 0,999996 près) : pendant le chat, le GPU reste au modèle de chat. Ceux des passages, des centaines à la fois, vont toujours sur le GPU à l'indexation : 219 passages en 7,8 s, contre 129 s sur le CPU. Ollama déplace le modèle une fois de l'un à l'autre (la première question après un `/index` prend ~1 s).

Mesuré sur le même projet (181 passages de code décrits, GPU de 6 Go, seuil par défaut 0.05), avec les filtres idéaux ; sans filtre, mêmes chiffres :

| | hit@4 | hit@20 | Hors sujet sans passage | Temps par passage | Projet entier |
| - | - | - | - | - | - |
| Sans descriptions | 0.77 | 0.91 | 5 sur 6 | – | – |
| Décrit par qwen3:8b | 0.73 | 0.95 | 5 sur 6 | 8 à 18 s | 25 à 45 min |
| **Décrit par qwen3:4b-instruct** (défaut) | **0.82** | **0.95** | **5 sur 6** | **~2 s** | **~6 min** |

- **Le rappel monte** : hit@20 0.91 → 0.95. Une question en français sur du code écrit en anglais (« carburant » face à `fuel`), absente des 20 candidats, passe au rang 1.
- **Le classement aussi**, au seuil par défaut : avec qwen3:4b-instruct, quatre questions gagnent des places (le calcul de la cible de deux variantes d'un algorithme, l'exploration par bruit, le choix du moteur d'un agent, les réseaux d'un module nommé), une en perd (les touches du clavier, du rang 3 au rang 14).
- Les descriptions de qwen3:8b resserraient les scores : plusieurs bonnes réponses passaient sous le seuil de 0.05 (hit@4 0.73 à 0.05, 0.86 à 0.01). Celles de qwen3:4b-instruct gardent le seuil par défaut utilisable (0.82 de 0.02 à 0.1). Sur 22 questions, ce sont des écarts d'une ou deux questions : à mesurer sur ses propres sources.

## Tester

```bash
python -m unittest discover -s tests     # depuis la racine du dépôt, ~2 s
```

Les tests (`tests/`) n'appellent aucun modèle : le reranker et le modèle qui décrit sont remplacés par des faux, la recherche se fait par mots-clés. Ils couvrent les genres et les motifs de chemin, les filtres (chemin, genre, date) appliqués avant le classement, le seuil et le repli sans reranker, ce qu'une source garde d'un `/index` à l'autre (exclusions, descriptions, versions), la migration d'un ancien index, les fichiers générés, les dates de l'historique git (ignorés sans git), le contexte des passages, la requête faite au modèle qui décrit et les messages de l'outil.

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
- hit@20 (0.86) est le plafond du reranker : il ne peut que réordonner ce que l'index lui donne. Les 3 questions manquées par l'index le restent (une question en français sur du code écrit en anglais, « maximum » face à une constante abrégée `MAX_…`, un fichier généré de 600 passages qui prend les places des mots-clés).
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
