# EV1 · Évaluation automatique et détection d'hallucinations

Un modèle, le **juge**, relit chaque réponse de Louis en arrière-plan une fois le tour fini, et la note. Les affirmations que les sources contredisent ou ne permettent pas de vérifier sont signalées.

## Ce qu'il fait

| Mesure | Comment | Échelle |
| ------ | ------- | ------- |
| **Fidélité aux sources** | la réponse est découpée en affirmations, chacune vérifiée contre ce que les outils ont lu : `supported`, `contradicted` ou `unverifiable`, avec la source et le passage cité | 0 à 1 |
| **Pertinence** | répond-elle à la question ? | 1 à 5 |
| **Cohérence** | claire, ordonnée, sans se contredire ? | 1 à 5 |

- **Sources** : les résultats de `search_knowledge`, `web_search`, `cat_file`, `search`, `git`, `run_code` (`eval.sources`). Les longues sources sont réduites aux passages dont parlent les affirmations ; une citation inventée par le juge est signalée.
- **Second regard** : chaque affirmation signalée (3 au plus, `eval.recheck`) est revérifiée seule.
- **Sans attente** : le juge tourne dans un fil, après le tour (`eval.background`), sur une partie des réponses si on veut (`eval.sample`). Une réponse sans source n'a pas de fidélité (`–`, pas 0).
- **Comparer des versions** : les notes vont dans les traces, `louis --dashboard` fait les moyennes par prompt et par modèle ; `python -m eval.bench` compare deux versions de Louis sur un jeu de questions fixe. Chaque résultat sauvegardé est aussi un échantillon RAGAS.

## Commandes

| Commande | Comment ça marche | À quoi ça sert |
| -------- | ----------------- | -------------- |
| `/eval` | montre les notes de la dernière réponse et les affirmations signalées ; attend le juge s'il est dessus, la juge maintenant si `eval.enabled` est coupé | vérifier une réponse |
| `louis --dashboard` | moyennes des notes par prompt et par modèle | suivre la qualité dans le temps |
| `python -m eval.bench <questions.json>` | Louis répond à chaque question dans une session neuve, le juge note | un benchmark avant de livrer |
| `… --save f.json` / `--baseline f.json` | garde un run / compare question par question | voir ce qu'un changement a amélioré ou cassé |
| `… --prompt <fichier>`, `--model <nom>`, `--judge <nom>`, `--traces <fichier>` | change le prompt, le modèle qui répond, le juge, enregistre les appels | comparer deux versions de Louis |

## Exemples

```
> /eval
⚖ Dernière réponse, notée par qwen3.5:9b en 24.0 s
  fidélité aux sources  33 %  (2 affirmations sur 6 appuyées par 1 source)
  pertinence            5/5  ...
  cohérence             5/5  ...
  ✗ contredite   « Le délai par défaut (TIMEOUT) est de 60 secondes. »
      [1] Lecture config.py : « TIMEOUT = 30 »
  ? invérifiable « La fonction load a été écrite en 2019. »
```

```bash
cd src
python -m eval.bench ../docs/eval_questions.json --save ../avant.json
python -m eval.bench ../docs/eval_questions.json --baseline ../avant.json --save ../apres.json --model qwen3:8b
```

Détails et réglages (`eval.*`) : [docs/EVAL.md](../../EVAL.md). Tests : `tests/test_eval.py`.
