# Cache sémantique

Quand on pose à Louis une question qu'il a déjà eue, dite autrement, il peut rendre tout de suite la réponse d'alors, sans demander au modèle : quelques dizaines de millisecondes au lieu de plusieurs secondes, et la carte graphique reste libre. C'est l'idée de [GPTCache](https://github.com/zilliztech/GPTCache) ou du cache sémantique de Redis.

**Désactivé par défaut** : une mauvaise réponse donnée tout de suite fait plus de mal qu'une bonne donnée lentement. Il faut d'abord mesurer les seuils sur ses propres questions (voir [Mesurer](#mesurer)).

## Utilisation

```bash
ollama pull nomic-embed-text      # le modèle d'embedding du RAG : il lit le sens des questions
cd src && python -m rag.reranker  # le reranker du RAG (installé par install.sh) : il vérifie que deux questions sont les mêmes

louis
> /cache on                       # active le cache pour ce lancement (cache.enabled: True pour toujours)
> Comment lire un fichier JSON en Python ?
  ...le modèle répond, la réponse est gardée
> /clear
> Comment on lit un fichier JSON avec Python ?
⚡ Réponse du cache (similarité 0.94), donnée il y a 2 min à « Comment lire un fichier JSON en Python ? »
  ...la même réponse, tout de suite
> /cache                          # ce qu'il garde, combien de fois il a répondu, son taux de réussite
> /cache forget                   # la dernière réponse qu'il a donnée était fausse : il l'oublie
> /cache clear                    # oublie toutes tes réponses
> /cache off
```

- La réponse donnée par le cache est gardée dans la session comme les autres : la conversation continue à partir d'elle.
- Le cache est un fichier SQLite : `louis.cache.db` dans le dossier courant, ou `~/.local/share/louis/louis.cache.db` avec le lanceur de `install.sh` (`LOUIS_CACHE` change le chemin). Il n'est créé qu'à la première réponse gardée.
- Sans `nomic-embed-text` (ou si Ollama est arrêté), le cache se tait et le modèle répond, comme d'habitude.
- Les réglages sont les `cache.*` de `src/config/settings.py`.

## Comment c'est fait

La question passe d'abord par le garde-fou (s'il est actif), puis par le cache, avant le modèle :

1. **Le sens.** La question est lue par le modèle d'embedding (sur le processeur, ~30 ms) et comparée aux questions gardées. Celles qui en sont assez proches (cosinus ≥ `cache.threshold`, 0.80) sont candidates.
2. **Les détails.** Un embedding lit la phrase, pas ses détails : « 17 × 23 » et « 17 × 24 » sont à 0.967. Une candidate doit parler des **mêmes nombres, fichiers et noms du code** (`snake_case`, `camelCase`, `NomDeClasse`, `fonction()`, ce qui est entre accents graves) que la question (`cache/rules.py`).
3. **La vérification.** Le cross-encoder du reranker (`rag.rerank.model`, le même modèle que le RAG, chargé une seule fois) relit chaque candidate avec la question, et ne rend sa réponse que s'il les trouve identiques (≥ `cache.rerank.min_score`, 0.35). Sans lui, les embeddings confondent des questions qui ne diffèrent que d'un mot (voir [Mesurer](#mesurer)) : **sans reranker (fastembed absent), le cache ne rend rien**, il garde seulement les réponses pour plus tard. `cache.rerank.enabled: False` se contente du sens, ce qui n'est pas sûr.

Le premier passage du reranker le charge (~2 s), les suivants prennent ~20 ms.

## Ce qui n'est jamais gardé

Louis lit et modifie des fichiers : la plupart de ses réponses dépendent du projet ou de la conversation, et ne valent plus rien plus tard. Le cache ne garde une réponse que si :

- **la question est la première de la session** (`cache.scope: "first"`). La suivante peut s'appuyer sur ce qui a été dit (« et pour la deuxième ? ») : `"any"` les prend toutes, à ses risques ;
- elle ne dépend pas **du moment** (« aujourd'hui », « maintenant », « dernière version », « today »...) ni **du projet tel qu'il est** (« ce fichier », « mon code », « ce projet », « here »...) ;
- le tour s'est terminé normalement (`done`) : ni coupé, ni annulé, ni en erreur, ni refusé par le garde-fou ;
- il n'a utilisé **aucun outil, ou seulement ceux de `cache.tools`** (`search_knowledge` par défaut), et aucun n'a échoué. Une réponse qui a lu ou modifié le projet, lancé du code, utilisé git ou cherché sur le web n'est jamais gardée ;
- en pas à pas (`/react`), la réponse n'a pas été donnée avec des problèmes que la vérification y avait trouvés ;
- ce n'est pas une réponse JSON (`/json`).

Ce qui est gardé, c'est ce que l'utilisateur a lu : la question telle que le garde-fou l'a laissée passer (masquée), et la réponse après ses rails de sortie. Une réponse gardée sans garde-fou n'est jamais rendue quand il est actif.

## Quand une réponse est oubliée

- Chaque réponse appartient à **un utilisateur** (`cache.shared: False`) : elle peut dire ce qu'il a indexé. **Un autre modèle ou un autre prompt système** n'y a pas accès non plus, ni un autre modèle d'embedding (ses vecteurs ne se comparent pas).
- Après `cache.ttl` (7 jours).
- Au-delà de `cache.max_entries` (1000) : celles servies le moins récemment partent d'abord.
- Quand la base de connaissances change (`/index` qui a modifié quelque chose, `/unindex`) : celles qui l'avaient consultée.
- `/cache forget`, `/cache clear`.

## Mesurer

```bash
cd src && python -m cache.evaluate [--json scores.json]
```

Le script lit 12 paires de paraphrases (la même question dite autrement : le cache devrait répondre) et 12 paires de presque-pareilles (des mots proches, une autre question : il ne doit jamais répondre), comme le cache les lit, et donne pour chaque seuil la part de chaque sorte à laquelle il répondrait.

Mesuré avec `nomic-embed-text` et `mmarco-mMiniLMv2-L12-H384-v1` :

| Méthode | Paraphrases servies | Presque-pareilles servies (erreurs) |
| --- | --- | --- |
| Sens seul, cosinus ≥ 0.92 | 50 % | **3 / 12** |
| Sens seul, cosinus ≥ 0.98 | 0 % | 1 / 12 |
| Sens ≥ 0.80 + détails + reranker ≥ 0.35 (**défaut**) | 42 % | **0 / 12** |

Le sens seul ne suffit à aucun seuil : « convertir une chaîne en entier » et « convertir un entier en chaîne » sont à **0.993**, « lire un fichier JSON » et « écrire un fichier JSON » à 0.975, plus que la plupart des vraies paraphrases (0.80 à 0.88). Le reranker les sépare (0.10 et 0.26 contre 0.36 à 0.81 pour les paraphrases qu'il accepte). Le prix est le rappel : il refuse aussi des paraphrases qui changent beaucoup de mots (« venv » pour « environnement virtuel », 0.003). Le cache rate donc des réponses qu'il aurait pu rendre, mais n'en rend pas de fausses.

Les questions qui lui sont posées dans la vraie vie ne sont pas celles du script : avant de l'activer pour de bon, ajouter les siennes à `SAME` et `OTHER` dans `src/cache/evaluate.py`.

## Suivi

Chaque question cherchée laisse une ligne `cache` dans `louis.traces.jsonl` (trouvée ou non, le score le plus proche, la durée, ou pourquoi elle n'a pas été cherchée), et le tour répondu par le cache est marqué `cached`. `louis --dashboard` donne le taux de réponses du cache et sa latence à côté de celle du modèle, sans que ses réponses en millisecondes ne cachent un modèle plus lent. Le juge (`eval.*`) ne relit pas les réponses du cache : il les a jugées quand le modèle les a données.
