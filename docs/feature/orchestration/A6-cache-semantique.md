# A6 · Cache sémantique

Une question déjà posée, même dite autrement et par un autre utilisateur, reçoit tout de suite la réponse d'alors, sans le modèle : quelques dizaines de millisecondes au lieu de plusieurs secondes, et la carte graphique reste libre. Actif par défaut.

## Ce qu'il fait

- **Le sens** : la question est lue par `nomic-embed-text` (~30 ms sur le CPU) et comparée aux questions gardées (cosinus ≥ `cache.threshold`, 0.78).
- **Les détails** : une candidate doit parler des mêmes nombres, fichiers et noms du code (« 17 × 23 » n'est pas « 17 × 24 »).
- **Le reranker** du RAG vérifie que les deux questions sont vraiment les mêmes : « lire un fichier JSON » n'a jamais la réponse de « écrire un fichier JSON ». S'il hésite, un petit modèle (`cache.match.model`) tranche.
- **Seulement les questions qui se comprennent seules** (« et pour la deuxième ? » ne l'est pas), qui ne dépendent ni du moment ni du projet.
- **Seulement les réponses sûres** : session où le modèle n'a encore rien lu du projet, pas d'autre outil que `search_knowledge`, tour fini normalement, réponse qui ne nomme pas l'utilisateur.
- **L'aide de Louis** : dès la première question d'une installation neuve, il répond aux questions sur Louis avec des réponses écrites par l'équipe (`src/cache/seed/`).
- **Oubli** : autre modèle ou autre prompt, après 7 jours (`cache.ttl`), au-delà de 1 000 réponses, quand la base de connaissances change.
- Partagé entre les utilisateurs de la machine (`cache.shared`). Préchauffé au lancement. Fichier SQLite `louis.cache.db` (`LOUIS_CACHE`).

## Commandes

| Commande | Comment ça marche | À quoi ça sert |
| -------- | ----------------- | -------------- |
| `/cache` | montre ce qu'il garde, combien de fois il a répondu, son taux de réussite, son seuil, son fichier | voir s'il sert |
| `/cache forget` | oublie la dernière réponse qu'il a donnée (une réponse de l'aide jusqu'au prochain changement de ses fichiers) | corriger une réponse fausse |
| `/cache clear` | oublie toutes les réponses gardées, pas l'aide de Louis | repartir d'un cache vide |
| `/cache off` / `/cache on` | coupe ou remet le cache pour ce lancement (`cache.enabled` pour toujours) | forcer une réponse du modèle |
| `cd src && python -m cache.evaluate [--json f.json]` | lit des paires de questions comme le cache, donne ce qu'il servirait à chaque seuil | régler `cache.threshold` sans risque |

## Exemples

```
> Comment lire un fichier JSON en Python ?
  ...le modèle répond, la réponse est gardée
> Comment on lit un fichier JSON avec Python ?
⚡ Réponse du cache (similarité 0.94), donnée il y a 2 min à « Comment lire un fichier JSON en Python ? »
> /cache            # ce qu'il garde, son taux de réussite
> /cache forget     # oublie la dernière réponse qu'il a donnée
> /cache clear      # oublie toutes les réponses (pas l'aide de Louis)
> /cache off        # pour ce lancement ; cache.enabled: False pour toujours
```

```bash
cd src && python -m cache.evaluate     # mesure les paraphrases servies et les erreurs, par seuil
```

Détails et mesures : [docs/CACHE.md](../../CACHE.md). Tests : `tests/test_cache.py`.
