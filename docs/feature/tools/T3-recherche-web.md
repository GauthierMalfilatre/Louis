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

Tests : `tests/test_web_search.py`.
