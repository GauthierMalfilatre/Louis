# Cache sémantique

Quand on pose à Louis une question qu'il a déjà eue, dite autrement, il rend tout de suite la réponse d'alors, sans demander au modèle : quelques dizaines de millisecondes au lieu de plusieurs secondes, et la carte graphique reste libre. C'est l'idée de [GPTCache](https://github.com/zilliztech/GPTCache) ou du cache sémantique de Redis.

Il est **actif par défaut**, et ses réponses sont **partagées entre les utilisateurs** de la machine. Dès la première question d'une nouvelle installation, il répond aussi aux questions sur Louis lui-même, avec des réponses écrites par l'équipe (voir [L'aide de Louis](#laide-de-louis)).

## Utilisation

```bash
ollama pull nomic-embed-text      # le modèle d'embedding du RAG : il lit le sens des questions
cd src && python -m rag.reranker  # le reranker du RAG (installé par install.sh) : il vérifie que deux questions sont les mêmes

louis
> Comment lire un fichier JSON en Python ?
  ...le modèle répond, la réponse est gardée
> Qu'est-ce qu'une closure ?
  ...le modèle répond, la réponse est gardée
> Comment on lit un fichier JSON avec Python ?
⚡ Réponse du cache (similarité 0.94), donnée il y a 2 min à « Comment lire un fichier JSON en Python ? »
  ...la même réponse, tout de suite
> Comment exporter ma session en PDF ?
⚡ Réponse de l'aide de Louis (similarité 0.96), à « Comment exporter une session en PDF ? »
> /cache                          # ce qu'il garde, combien de fois il a répondu, son taux de réussite
> /cache forget                   # la dernière réponse qu'il a donnée était fausse : il l'oublie
> /cache clear                    # oublie toutes les réponses gardées (pas l'aide de Louis)
> /cache off                      # pour ce lancement ; cache.enabled: False pour toujours
```

- La réponse donnée par le cache est gardée dans la session comme les autres : la conversation continue à partir d'elle.
- Le cache est un fichier SQLite : `louis.cache.db` dans le dossier courant, ou `~/.local/share/louis/louis.cache.db` avec le lanceur de `install.sh` (`LOUIS_CACHE` change le chemin).
- Sans `nomic-embed-text` (ou si Ollama est arrêté), le cache se tait et le modèle répond, comme d'habitude. Sans le reranker, il ne rend que les questions écrites à l'identique.
- Les réglages sont les `cache.*` de `src/config/settings.py`.

## Comment c'est fait

La question passe d'abord par le garde-fou (s'il est actif), puis par le cache, avant le modèle :

1. **Le sens.** La question est lue par le modèle d'embedding (sur le processeur, ~30 ms) et comparée aux questions gardées. Celles qui en sont assez proches (cosinus ≥ `cache.threshold`, 0.80) sont candidates.
2. **Les détails.** Un embedding lit la phrase, pas ses détails : « 17 × 23 » et « 17 × 24 » sont à 0.967. Une candidate doit parler des **mêmes nombres, fichiers et noms du code** (`snake_case`, `camelCase`, `NomDeClasse`, `fonction()`, ce qui est entre accents graves) que la question (`cache/rules.py`).
3. **La vérification.** Une candidate écrite comme la question (à la casse, aux accents et à la ponctuation près) est rendue telle quelle. Les autres sont relues par le cross-encoder du reranker (`rag.rerank.model`, le même modèle que le RAG, chargé une seule fois) :
   - une réponse du modèle : sa **question** est relue avec la nouvelle, et rendue si le reranker les trouve identiques (≥ `cache.rerank.min_score`, 0.35) ;
   - une réponse de l'aide de Louis : sa **réponse** est relue avec la nouvelle question (≥ `cache.seed.min_score`, 0.75).

   Pourquoi deux façons : le reranker a appris à dire si un passage répond à une question, pas si deux questions sont les mêmes. Relue avec une réponse du modèle sur la lecture d'un JSON, « comment écrire un fichier JSON ? » obtient 0.977 (la réponse parle bien de fichiers JSON) : seules les questions se comparent sans risque. Les réponses de l'aide de Louis, elles, disent tout ce que Louis fait sur un sujet : les relire avec la question en trouve bien plus.

Sans le reranker, les embeddings confondent des questions qui ne diffèrent que d'un mot (voir [Mesurer](#mesurer)). `cache.rerank.enabled: False` se contente du sens, ce qui n'est pas sûr. Le premier passage du reranker le charge (~2 s), les suivants prennent ~20 ms.

## Quelles questions, quelles réponses

**N'importe quelle question de la session est cherchée, si elle se comprend seule.** « Et pour la deuxième ? », « pourquoi ? », « corrige-le », « ta réponse est fausse », « what about the second one? » s'appuient sur ce qui a été dit avant : ni cherchées, ni gardées. Le cache les reconnaît à leurs mots (« et », « mais » au début, « ça », « le deuxième » seul, « ta réponse », « it »...) et à leur longueur (moins de 3 mots). Il en rate parfois une qui se comprenait seule (« Comment ça marche, un décorateur ? ») : le modèle y répond, rien de faux n'est donné.

Les questions qui dépendent **du moment** (« aujourd'hui », « maintenant », « dernière version », « today »...) ou **du projet tel qu'il est** (« ce fichier », « mon code », « ce projet », « here »...) ne sont jamais cherchées.

**Une réponse n'est gardée que si elle vaut encore plus tard, pour un autre :**

- la session est **propre** : le modèle n'y a encore rien lu du projet (aucun outil sauf `search_knowledge`, `cache.tools`). Une fois qu'il a lu `app.py`, ce qu'il dit ensuite peut s'en servir, même à une question générale ; les réponses du cache restent données dans cette session, mais plus rien n'y est gardé ;
- le tour lui-même n'a utilisé **aucun outil, ou seulement ceux de `cache.tools`**, et aucun n'a échoué ;
- le tour s'est terminé normalement (`done`) : ni coupé, ni annulé, ni en erreur, ni refusé par le garde-fou ;
- la réponse **ne nomme pas l'utilisateur** (« Bonjour Ada, ... ») : un autre la recevrait ;
- en pas à pas (`/react`), elle n'a pas été donnée avec des problèmes que la vérification y avait trouvés ;
- ce n'est pas une réponse JSON (`/json`).

Ce qui est gardé, c'est ce que l'utilisateur a lu : la question telle que le garde-fou l'a laissée passer (masquée), et la réponse après ses rails de sortie. Une réponse gardée sans garde-fou n'est jamais rendue quand il est actif.

## Partage entre les utilisateurs

Les utilisateurs de Louis (`--user`) sont des profils sur une même machine : le lanceur de `install.sh` leur donne déjà la même base de sessions et la même base de connaissances. Le cache est partagé de la même façon (`cache.shared: True`) : une question posée par l'un est répondue tout de suite pour les autres, y compris pour un profil qui vient d'être créé. Le nom de l'utilisateur et la date, que Louis ajoute après le prompt système, ne comptent pas : les réponses servent d'un utilisateur à l'autre.

`cache.shared: False` donne à chacun ses propres réponses : pour un `louis --web --host 0.0.0.0` ouvert à des personnes qui ne doivent pas lire les réponses des autres.

## L'aide de Louis

Une installation neuve n'a encore rien gardé. Pour que le cache serve dès la première question, Louis arrive avec des réponses **écrites par l'équipe** sur Louis lui-même : ses commandes, la base de connaissances, l'export, le partage, l'interface web, la sandbox, l'installation... Elles sont dans `src/cache/seed/*.jsonl`, une réponse par ligne avec les façons de poser la question :

```json
{"questions": ["Comment indexer un dossier ?", "Comment ajouter de la documentation à la base de connaissances ?"], "answer": "Avec `/index <dossier> [nom]`..."}
```

- Elles sont rangées dans le même `louis.cache.db` (pas de base à part), à la première question, puis de nouveau chaque fois que les fichiers changent (leur version est le hash de leur contenu). La première fois prend une ou deux secondes : chaque question est lue par le modèle d'embedding.
- Elles valent pour tous les modèles, tous les prompts et tous les utilisateurs, n'expirent jamais, ne comptent pas dans `cache.max_entries`, et `/cache clear` les laisse. `/cache forget` en oublie une jusqu'au prochain changement des fichiers. `cache.seed: False` les retire.
- **Pour qu'elle réponde à plus de questions, il faut y écrire plus de façons de les poser.** Une question écrite dans le fichier est toujours rendue ; une autre ne l'est que si le reranker est sûr de lui (≥ 0.75, voir [Mesurer](#mesurer)).
- Aucune n'est vérifiée par un modèle : elles doivent être justes, et vraies quelle que soit la session (pas de « ce fichier », pas de date). Après un changement de Louis (une commande renommée...), il faut les mettre à jour.

## Quand une réponse est oubliée

- Chaque réponse du modèle n'est donnée que pour **le même modèle et le même prompt système** (un autre y répondrait autrement), et le même modèle d'embedding (ses vecteurs ne se comparent pas).
- Après `cache.ttl` (7 jours).
- Au-delà de `cache.max_entries` (1000) : celles servies le moins récemment partent d'abord.
- Quand la base de connaissances change (`/index` qui a modifié quelque chose, `/unindex`) : celles qui l'avaient consultée.
- `/cache forget`, `/cache clear`.

## Mesurer

```bash
cd src && python -m cache.evaluate [--json scores.json]
```

Le script lit des paires de questions comme le cache les lit, et donne pour chaque seuil la part de chaque sorte à laquelle il répondrait :

- 12 paraphrases (la même question dite autrement : le cache devrait répondre) et 12 presque-pareilles (des mots proches, une autre question : il ne doit jamais répondre) ;
- pour l'aide de Louis, 10 questions sur Louis dites autrement que dans le fichier, et 10 questions de code qui lui ressemblent (« indexer une liste en Python », « installer numpy »...).

Mesuré avec `nomic-embed-text` et `mmarco-mMiniLMv2-L12-H384-v1` :

| Réponses du modèle | Paraphrases servies | Presque-pareilles servies (erreurs) |
| --- | --- | --- |
| Sens seul, cosinus ≥ 0.92 | 50 % | **3 / 12** |
| Sens seul, cosinus ≥ 0.98 | 0 % | 1 / 12 |
| Sens ≥ 0.80 + détails + reranker sur la question ≥ 0.35 (**défaut**) | 42 % | **0 / 12** |

| Aide de Louis | Questions sur Louis servies | Questions de code servies (erreurs) |
| --- | --- | --- |
| Reranker sur la réponse ≥ 0.60 | 50 % | **1 / 10** |
| Reranker sur la réponse ≥ 0.75 (**défaut**) | 20 % | **0 / 10** |

Le sens seul ne suffit à aucun seuil : « convertir une chaîne en entier » et « convertir un entier en chaîne » sont à **0.993**, « lire un fichier JSON » et « écrire un fichier JSON » à 0.975, plus que la plupart des vraies paraphrases (0.80 à 0.88). Le reranker les sépare (0.10 et 0.26 contre 0.36 à 0.81 pour les paraphrases qu'il accepte). Pour l'aide de Louis, « valider un JSON avec un schéma en Python » obtient 0.74 avec la réponse sur `/json` : d'où 0.75.

Le prix est le rappel : le cache refuse aussi des paraphrases qui changent beaucoup de mots (« venv » pour « environnement virtuel »). Il rate donc des réponses qu'il aurait pu rendre, mais n'en rend pas de fausses sur ces jeux. Ils sont petits : avant de changer un seuil, ajouter des questions réelles à `SAME`, `OTHER`, `SEED_SAME` et `SEED_OTHER` dans `src/cache/evaluate.py`.

## Suivi

Chaque question cherchée laisse une ligne `cache` dans `louis.traces.jsonl` (trouvée ou non, le score le plus proche, la durée, ou pourquoi elle n'a pas été cherchée), et le tour répondu par le cache est marqué `cached`. `louis --dashboard` donne le taux de réponses du cache et sa latence à côté de celle du modèle, sans que ses réponses en millisecondes ne cachent un modèle plus lent. Le juge (`eval.*`) ne relit pas les réponses du cache : il les a jugées quand le modèle les a données.
