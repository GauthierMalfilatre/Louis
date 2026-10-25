# T3 · Recherche web

Avec l'outil `web_search`, le modèle cherche sur internet (DuckDuckGo, par `ddgs`) ce qu'il ne sait pas ou ce qui est récent, lit les résultats et répond avec, en citant ses sources.

## Ce qu'il fait

- **Requête** : `web_search(query, max_results?)`, le modèle choisit lui-même les mots. Pas de clé d'API.
- **Résultats** : une liste JSON `{title, url, snippet}` injectée dans le contexte, que le modèle lit avant de répondre.
- **La date** est donnée au modèle après son prompt système : il sait ce que « récent » veut dire.
- **Erreurs** (pas de réseau, limite de DuckDuckGo) : rendues au modèle, qui le dit ou fait autrement.
- **Garde-fou** : avec [EV2](../evaluation/EV2-garde-fous.md), une requête qui contient un secret ou une donnée personnelle est refusée avant de quitter la machine.
- Les résultats sont des **sources** pour le juge ([EV1](../evaluation/EV1-eval-hallucinations.md)), et ne sont jamais gardés par le cache sémantique.

## Commandes

| Commande | Comment ça marche | À quoi ça sert |
| -------- | ----------------- | -------------- |
| `web_search(query, max_results?)` (outil du modèle) | interroge DuckDuckGo et rend `{title, url, snippet}` en JSON | répondre sur ce qui est récent ou inconnu du modèle, avec des sources |
| une question qui en a besoin | le modèle décide seul d'appeler l'outil, puis répond avec les résultats | rien à taper de plus : « quelle est la dernière version de Python ? » |

## Exemple

```
> Quelle est la dernière version de Python ?
  ● Recherche web « dernière version Python »
    ⎿ 5 résultats
La dernière version stable est Python 3.14 (python.org/downloads).
```

## Mesure réelle : avec et sans

`qwen3.5:9b` sur le processeur, `chat.context` à 12 288, nouvelle session à chaque fois. La mesure date du 24 octobre 2026. La question : « Quelle est la dernière version stable de Python publiée à ce jour, et à quelle date est-elle sortie ? ». On regarde si la réponse est à jour.

| | Sans `web_search` | Avec `web_search` |
| - | - | - |
| Réponse | « Python 3.12, sortie le 21 octobre 2023 », et la 3.13 serait « en bêta » ✗ | « Python 3.15.0, publiée le 9 octobre 2026 », puis la 3.15.1 du 21 octobre ✓ |
| Outils appelés | aucun | `web_search` ×2 |
| Appels au modèle / tokens de prompt | 1 / 3 733 | 3 / 13 752 |
| Temps | 285 s | 430 s |

Sans le web, le modèle répond depuis ses données d'entraînement, vieilles de trois ans. Il le dit, mais il donne quand même une réponse fausse. Avec le web, la réponse est celle du jour. Ça coûte deux recherches, ~10 000 tokens de résultats à lire et 2 min 30 de plus.

Tests : `tests/test_web_search.py`.
