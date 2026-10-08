# Évaluation des réponses (LLM juge)

Un modèle, le **juge**, relit chaque réponse de Louis une fois son tour fini, et la note :

| Mesure | Comment | Échelle |
| ------ | ------- | ------- |
| **Fidélité aux sources** | la réponse est découpée en affirmations atomiques (sans voir les sources), puis chacune est vérifiée contre ce que les outils ont lu : `supported`, `contradicted` ou `unverifiable`, avec le numéro de la source et le passage cité | part des affirmations appuyées, 0 à 1 |
| **Pertinence** | répond-elle à la question ? grille avec un repère par note, la raison avant la note | 1 à 5 |
| **Cohérence** | claire, ordonnée, sans se contredire ? | 1 à 5 |

Un petit juge ne retrouve pas une ligne dans un long fichier (mesuré : qwen3:4b-instruct et qwen3:8b disaient « invérifiable » pour un fait de `app/app.py`, 21 000 caractères, et le trouvaient avec les 600 caractères autour). Comme FActScore, les longues sources sont d'abord réduites aux passages dont parlent les affirmations (`eval/focus.py`) : fenêtres de lignes classées par les mots de chaque affirmation (identifiants coupés : `SAME_CALLS` → `same`, `calls`), puis relues par le cross-encoder multilingue de la base de connaissances s'il est installé (`rag.rerank.*`). Avec ça, les deux juges trouvent le fait, avec la bonne citation.

Les affirmations **contredites** ou **invérifiables** sont signalées. Une réponse qui n'a lu aucune source (de mémoire) n'a pas de fidélité (`–`, pas 0) : ses affirmations sont toutes invérifiables. Le juge vérifie aussi que le passage qu'il cite est bien dans la source : une citation inventée est signalée.

## Pourquoi une évaluation directe (et pas par paires)

- Les deux critères du sujet sont directs par nature : signaler une affirmation, c'est la comparer à **ses sources**, pas à une autre réponse. Et une note par réponse se suit dans le temps, par version (tableau de bord).
- Un petit juge (qwen3.5:9b) place mal une réponse sur une large échelle, mais choisit bien entre trois mots : la fidélité repose sur des verdicts par affirmation, les grilles ont un repère par note, la température est à 0.
- La comparaison **par paires** (A contre B, dans les deux ordres) est plus fiable pour départager deux versions proches en pertinence et en cohérence : elle viendra en mode hors ligne, sur deux runs sauvegardés par le benchmark (les réponses y sont gardées entières).

## Où il s'insère

- **Bus d'événements** : le juge n'écoute que le bus, comme le monitoring. Il lit la question, les résultats des outils de `eval.sources`, la dernière réponse du tour (celle qui n'appelle pas d'outil), et publie `EVAL_SCORED` : le recorder en fait un enregistrement `eval` dans `louis.traces.jsonl`.
- **Outils** : le juge n'est pas un outil du modèle (un modèle qui se juge pendant son tour se flatte, et ralentit la réponse). Les outils sont ses **sources** : `search_knowledge`, `web_search`, `cat_file`, `search`, `git`, `run_code`.
- **Garde-fou (NeMo)** : un rail bloque ou masque pendant le tour ; le juge mesure après, sans rien changer. Il ne lit que ce que le garde-fou a laissé passer (question masquée, résultats filtrés) : aucune nouvelle fuite. Une réponse refusée par le garde-fou n'est pas jugée. Les sources sont données au juge comme des données, jamais des ordres.

## Utilisation

```
> /eval
⚖ Dernière réponse, notée par qwen3.5:9b en 24.0 s
  fidélité aux sources  33 %  (2 affirmations sur 6 appuyées par 1 source)
  pertinence            5/5  ...
  cohérence             5/5  ...
  ✗ contredite   « Le délai par défaut (TIMEOUT) est de 60 secondes. »
      [1] Lecture config.py : « TIMEOUT = 30 »
  ? invérifiable « La fonction load a été écrite en 2019. »
      Aucune source ne mentionne l'année de création de la fonction load.
```

Avec `eval.enabled`, chaque réponse est jugée **en arrière-plan** : l'utilisateur n'attend jamais, et le juge ne demande rien au modèle pendant que Louis répond (le GPU reste au chat). Les notes vont dans les traces, `/eval` montre celles de la dernière réponse (en l'attendant si le juge est dessus). Sans `eval.enabled`, `/eval` juge la dernière réponse à la demande. `louis --dashboard` montre les moyennes, par prompt et par modèle.

Chaque réponse jugée coûte 2 ou 3 requêtes au modèle (environ 80 s avec qwen3:8b sur un GPU de portable, autant de temps où le GPU sert au juge entre deux messages) : `eval.sample` n'en juge qu'une partie.

## Benchmark : comparer deux versions avant de les livrer

```bash
cd src
python -m eval.bench ../docs/eval_questions.json --save ../avant.json
# changer le prompt (--prompt fichier), le modèle (--model qwen3:8b), ou le code
python -m eval.bench ../docs/eval_questions.json --baseline ../avant.json --save ../apres.json
```

Louis répond à chaque question dans une nouvelle session, avec tous ses outils (en lecture seule : personne n'accorde de permission), son garde-fou et sa base de connaissances. Le run affiche les notes et les affirmations signalées de chaque question, les moyennes par `kind`, et ce qui a changé depuis `--baseline`. `--judge` choisit un autre juge : un modèle d'une autre famille juge plus équitablement (un modèle a tendance à préférer ses propres réponses).

## RAGAS

Chaque résultat sauvegardé par `--save` contient `ragas` : `user_input`, `retrieved_contexts`, `response` et `reference`, les champs d'un `SingleTurnSample` de RAGAS. La fidélité de Louis suit la définition de celle de RAGAS (part des affirmations appuyées par le contexte) : les deux se comparent.

## Réglages (`src/config/settings.py`)

| Réglage | Défaut | |
| ------- | ------ | - |
| `eval.enabled` | `True` | juger chaque réponse (sinon : seulement avec `/eval`) |
| `eval.background` | `True` | dans un thread, sans faire attendre l'utilisateur |
| `eval.sample` | `1.0` | part des réponses jugées |
| `eval.model` | `None` | le juge (`None` : le modèle du chat, déjà chargé) |
| `eval.context` | `16384` | son `num_ctx` quand ce n'est pas le modèle du chat |
| `eval.sources` | `[search_knowledge, web_search, cat_file, search, git, run_code]` | les outils dont les résultats sont des sources |
