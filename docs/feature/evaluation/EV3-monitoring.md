# EV3 · Logs et tableau de bord

Chaque appel au modèle et aux outils est enregistré, une ligne JSON par événement, dans `louis.traces.jsonl` (à côté de `louis.db` ; `LOUIS_TRACES` change le chemin). `louis --dashboard` en fait des métriques.

## Ce qui est enregistré

| Type | Contenu |
| ---- | ------- |
| `run` | un lancement : le modèle, les réglages qui jouent sur la vitesse |
| `prompt` | un prompt système, en entier la première fois ; les autres lignes le nomment par sa version (son hash) |
| `llm` | une requête au modèle : à quoi elle sert (`reply`, `structured`, `check`, `summary`), ce qu'on lui donne, sa réponse, les outils demandés, la latence, le premier token, les tokens, le chargement, le statut (`ok`, `error`, `cancelled`) |
| `tool` | un appel d'outil : arguments, succès, durée, début du résultat, temps d'attente de ta permission |
| `turn` | une réponse complète : comment elle a fini, temps total, tokens, tours ; étapes et vérifications (`/react`), plans, `cached` |
| `guard`, `rag`, `cache`, `structured`, `step`, `check`, `plan`, `eval` | ce que chaque feature a fait : un rail déclenché, une recherche et ses passages, une question cherchée dans le cache, un plan et sa décision, une réponse notée… |

Les lignes d'un tour partagent son `turn`. Les textes longs sont coupés, et masqués comme dans `louis.log`. Le temps passé à attendre ta permission est retiré des latences.

## Le tableau de bord

- Volume d'appels, latence (p50, p95), premier token, vitesse, taux d'erreur, tokens par appel, outils et leurs erreurs, réponses qui ont échoué et appels les plus lents.
- Sur le dernier jour, 7 jours, 30 jours ou tout ; une courbe par heure ou par jour.
- **Dérives** en tête : chaque nouveau prompt ou modèle est comparé à celui qu'il remplace, et les dernières 24 h à la semaine d'avant. Alerte au-delà de ±30 % de latence médiane, ±30 % de tokens par appel ou ±5 points d'erreurs, avec au moins 5 appels de chaque côté.
- Une page HTML autonome (`louis.dashboard.html`), sans serveur, plus un résumé dans le terminal.

## Commandes

| Commande | Comment ça marche | À quoi ça sert |
| -------- | ----------------- | -------------- |
| `louis --dashboard` | lit `louis.traces.jsonl`, affiche le résumé, écrit et ouvre `louis.dashboard.html` | voir les métriques et les dérives |
| `cd src && python -m monitor [traces] [-o page.html] [--open]` | la même chose sur un autre fichier de traces, vers une autre page | analyser les traces d'un autre poste ou d'un benchmark |
| `LOUIS_TRACES=<fichier>` | change le fichier où Louis écrit ses traces | séparer des expériences |

## Exemples

```bash
louis --dashboard                       # ou : python src/main.py --dashboard
cd src && python -m monitor ../louis.traces.jsonl -o /tmp/dashboard.html --open
```

```
Drift
  ⚠ prompt 3f2a1c → 9b7e04 (since 23 Oct 14:02, 12 → 48 calls)
      ▲ median latency 2.10 s → 4.30 s (+105%)
      ▲ prompt tokens per call 1840 → 3950 (+115%)
```

Tests : `tests/test_monitor.py`, `tests/test_dashboard.py`.
