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

La question passe par le cache **avant le garde-fou** et avant le modèle. Le garde-fou ne relit que les questions auxquelles le cache n'a pas de réponse (voir [Garde-fou](#garde-fou)) :

1. **Le sens.** La question est lue par le modèle d'embedding (sur le processeur, ~30 ms) et comparée aux questions gardées. Celles qui en sont assez proches (cosinus ≥ `cache.threshold`, 0.78) sont candidates.
2. **Les détails.** Un embedding lit la phrase, pas ses détails : « 17 × 23 » et « 17 × 24 » sont à 0.967. Une candidate doit parler des **mêmes nombres, fichiers et noms du code** (`snake_case`, `camelCase`, `NomDeClasse`, `fonction()`, ce qui est entre accents graves) que la question (`cache/rules.py`).
3. **Le reranker (~20 ms).** Une candidate écrite comme la question (à la casse, aux accents et à la ponctuation près) est rendue telle quelle. Les autres sont relues par le cross-encoder du reranker (`rag.rerank.model`, le même modèle que le RAG, chargé une seule fois) :
   - une réponse du modèle : sa **question** est relue avec la nouvelle, et rendue si le reranker les trouve identiques (≥ `cache.rerank.min_score`, 0.35) ;
   - une réponse de l'aide de Louis : sa **réponse** est relue avec la nouvelle question (≥ `cache.seed.min_score`, 0.75).

   Pourquoi deux façons : le reranker a appris à dire si un passage répond à une question, pas si deux questions sont les mêmes. Relue avec une réponse du modèle sur la lecture d'un JSON, « comment écrire un fichier JSON ? » obtient 0.977 (la réponse parle bien de fichiers JSON) : seules les questions se comparent sans risque. Les réponses de l'aide de Louis, elles, disent tout ce que Louis fait sur un sujet.
4. **Le petit modèle (~2,7 s).** Le reranker n'a jamais confirmé une mauvaise question, mais il en rate la plupart des bonnes : « Tu peux me redire comment fonctionne le système de fuel ? » obtient 0.010 contre « Comment marche le système de fuel ? ». Les deux candidates les plus proches qu'il n'a pas confirmées sont donc posées à un petit modèle (`cache.match.model`, `qwen3:4b-instruct`, celui du scribe, sur le processeur) : « une seule et même réponse répond-elle aux deux ? ». Il a le dernier mot (`cache/matcher.py`).

   Il ne coûte rien quand aucune question gardée n'est assez proche, ~2,7 s par candidate sinon (deux au plus) : une réponse du cache arrive alors en ~3 s au lieu de plusieurs dizaines, et une question qui n'en a pas (« écrire » après « lire ») attend ces secondes en plus avant le modèle. `cache.match.model: ""` s'en passe : le reranker seul.

Sans reranker ni petit modèle, les embeddings confondent des questions qui ne diffèrent que d'un mot (voir [Mesurer](#mesurer)) : le cache ne rend alors que les questions écrites à l'identique. `cache.rerank.enabled: False` se contente du sens, ce qui n'est pas sûr.

**Préchauffage.** Au lancement, pendant que l'utilisateur tape sa première question, trois fils chargent le modèle d'embedding (en lisant les questions de l'aide de Louis si elles ont changé), le reranker et le petit modèle. La première question les attend s'ils n'ont pas fini. Sur une installation neuve, c'était ~12 s de plus sur la première question (6,8 s pour l'aide, 5,8 s pour le reranker, d'après un log) ; préchauffé, la réponse de l'aide arrive en ~0,15 s quand le reranker la confirme.

## Garde-fou

Avec le garde-fou actif (`guard.enabled`), chaque message est relu par le modèle contre ses règles avant d'arriver au modèle : plusieurs secondes, et plus d'une minute sur le premier message d'un lancement (79 s dans un log). Le cache passe **avant** lui :

- **Une question à laquelle le cache répond n'est pas relue par le garde-fou.** L'utilisateur ne reçoit qu'une réponse que les rails de sortie ont vérifiée quand elle a été gardée (ou écrite par l'équipe), donnée à une question que les rails d'entrée avaient laissée passer, et que le reranker ou le petit modèle trouve identique. Au pire, la réponse ne convient pas ; jamais une réponse que le garde-fou aurait refusée. Le message est quand même masqué avant d'être gardé dans la session, par les motifs du garde-fou (adresses, clés, cartes... sans modèle, instantané).
- **Une question à laquelle il ne répond pas passe par le garde-fou comme avant**, puis par le modèle. Si les rails d'entrée l'ont masquée (elle contenait une adresse, une clé...), sa réponse n'est jamais gardée : le cache l'avait cherchée telle qu'elle était tapée, et la partagerait avec les autres utilisateurs.
- Une réponse gardée sans garde-fou n'est jamais rendue quand il est actif.

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

Ce qui est gardé, c'est ce que l'utilisateur a lu : la question que le garde-fou a laissée passer sans rien masquer, et la réponse après ses rails de sortie.

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
- Une question écrite dans le fichier est toujours rendue ; une autre l'est si le reranker la confirme sur la réponse (≥ 0.75) ou si le petit modèle la trouve identique à l'une des façons écrites : 7 des 10 questions sur Louis du jeu de test (voir [Mesurer](#mesurer)).
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

- 16 paraphrases (la même question dite autrement : le cache devrait répondre) et 16 presque-pareilles (des mots proches, une autre question : il ne doit jamais répondre), dont « comment marche le système de fuel » contre « tu peux me redire comment fonctionne… » ou « comment modifier… » ;
- pour l'aide de Louis, 10 questions sur Louis dites autrement que dans le fichier, et 10 questions de code qui lui ressemblent (« indexer une liste en Python », « installer numpy »...).

Pour chaque seuil, il donne ce que le cache sert avec le reranker seul et avec le petit modèle, et combien de presque-pareilles sont posées au petit modèle (le coût des questions sans réponse). Mesuré avec `nomic-embed-text`, `mmarco-mMiniLMv2-L12-H384-v1` et `qwen3:4b-instruct` :

| Réponses du modèle (seuil 0.78) | Paraphrases servies | Presque-pareilles servies (erreurs) |
| --- | --- | --- |
| Sens seul (et détails), cosinus ≥ 0.92 | 6 / 16 | **5 / 16** |
| + détails + reranker ≥ 0.35 | 4 / 16 | **0 / 16** |
| + petit modèle (**défaut**) | **15 / 16** | **0 / 16** |

| Aide de Louis (seuil 0.78) | Questions sur Louis servies | Questions de code servies (erreurs) |
| --- | --- | --- |
| Reranker sur la réponse ≥ 0.60 | 5 / 10 | **1 / 10** |
| Reranker sur la réponse ≥ 0.75 | 2 / 10 | **0 / 10** |
| + petit modèle (**défaut**) | **7 / 10** | **0 / 10** |

Le sens seul ne suffit à aucun seuil : « convertir une chaîne en entier » et « convertir un entier en chaîne » sont à **0.993**, « lire un fichier JSON » et « écrire un fichier JSON » à 0.975, plus que la plupart des vraies paraphrases (0.80 à 0.88). Le reranker ne se trompe pas mais confirme peu ; le petit modèle reconnaît « Tu sais faire quoi ? », « venv » pour « environnement virtuel » ou « Tu peux me redire comment fonctionne le système de fuel ? », et refuse toujours « écrire » pour « lire », « modifier le système de fuel », « Qu'est-ce que tu ne sais pas faire ? ».

Le seuil de 0.78 vient de la même mesure : il trouve « Que fait yield ? » (0.795) sans poser plus de questions au petit modèle qu'à 0.80 ; plus bas, rien de plus n'est trouvé, et de plus en plus de questions sans réponse lui sont posées (jusqu'à 9 sur 10 pour l'aide de Louis à 0.66, ~2,7 s chacune).

Il reste des ratés : « 17 fois 23, **ça** fait combien ? » est pris pour une suite (« ça » renvoie d'habitude à ce qui précède), et le petit modèle refuse encore quelques vraies paraphrases (« couper » pour « désactiver le cache »). Les jeux de test sont petits : avant de changer un seuil, ajouter des questions réelles à `SAME`, `OTHER`, `SEED_SAME` et `SEED_OTHER` dans `src/cache/evaluate.py`.

## Suivi

Chaque question cherchée laisse une ligne `cache` dans `louis.traces.jsonl` (trouvée ou non, le score le plus proche, la durée, combien de questions ont été posées au petit modèle, ou pourquoi elle n'a pas été cherchée), et le tour répondu par le cache est marqué `cached`. `louis --dashboard` donne le taux de réponses du cache et sa latence à côté de celle du modèle, sans que ses réponses en millisecondes ne cachent un modèle plus lent. Le juge (`eval.*`) ne relit pas les réponses du cache : il les a jugées quand le modèle les a données.
