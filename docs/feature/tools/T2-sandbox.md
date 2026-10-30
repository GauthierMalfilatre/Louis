# T2 · Exécution de code isolée (sandbox)

Avec l'outil `run_code`, Louis teste du code avant de l'écrire ou de répondre : il lit la sortie et les erreurs, et corrige son code s'il le faut. Le code tourne dans un conteneur Docker, après que l'utilisateur l'a lu et autorisé.

## Ce qu'il fait

- **Langages** : `python`, `sh`, `c`, `cpp`, `go`, `rust`, bibliothèque standard seulement.
- **Isolé** : sans réseau, sans accès au projet, disque en lecture seule (sauf un petit `/tmp`), sans privilèges, en utilisateur `nobody`.
- **Limité** : en temps (10 s ; 30 s pour c et c++ ; 1 min pour go et rust, compilation comprise), en mémoire et en nombre de processus. Le programme est tué au-delà.
- **Sortie** : stdout, stderr et le code de retour reviennent au modèle, `sandbox.output` octets au plus pour chacun.
- **Images** : jamais téléchargées par Louis. Sans Docker, l'outil n'est pas proposé. `sandbox.languages` change l'image, le temps ou la mémoire d'un langage.

## Commandes

| Commande | Comment ça marche | À quoi ça sert |
| -------- | ----------------- | -------------- |
| `run_code(language, code)` (outil du modèle) | montre le code, demande ton accord, l'exécute dans un conteneur jetable, rend stdout, stderr et le code de retour | tester une idée, un calcul, un script, et corriger ses erreurs |
| `docker pull python:3.13-alpine alpine:latest golang:alpine rust:alpine gcc:latest` | télécharge les images, une fois | rendre l'outil utilisable (Louis ne télécharge jamais rien) |
| `sandbox.enabled`, `sandbox.output`, `sandbox.languages` | réglages de `src/config/settings.py` | couper l'outil, changer la sortie gardée, l'image, le temps ou la mémoire d'un langage |

## Exemples

```bash
docker pull python:3.13-alpine alpine:latest golang:alpine rust:alpine gcc:latest
```

```
> Vérifie que ma fonction de tri marche sur une liste vide
  ● run_code python            ← le code est montré, tu l'autorises
    ⎿ IndexError: list index out of range
  ● run_code python            ← corrigé, relancé
    ⎿ [] [1, 2, 3]
La liste vide plantait (IndexError) : j'ai ajouté un test au début de la fonction.
```

```python
"sandbox.languages": {"cpp": {"image": "gcc:14-bookworm", "timeout": 60}}   # src/config/settings.py
```

## Mesure réelle : avec et sans

`qwen3.5:9b` sur le processeur, `chat.context` à 12 288, nouvelle session à chaque question. Ce sont deux calculs qu'on ne fait pas de tête. On regarde la justesse.

| | Sans sandbox (`sandbox.enabled: False`) | Avec sandbox |
| - | - | - |
| Nombres premiers < 200 000 (vrai : 17 984) | « 18 031 » ✗ | « 17 984 » ✓ |
| SHA-256 de « louis », 12 premiers caractères (vrai : `5f16795c54ab`) | « `4b4c8f5a5c0a` » ✗ | « `5f16795c54ab` » ✓ |
| Outils appelés | `run_code` ✗ (inconnu), puis `web_search` ×2 / `run_code` ✗ | `run_code` / `run_code` |
| Appels au modèle | 4 et 3 | 2 et 2 |
| Temps | 478 s et 367 s | 330 s et 321 s |

Sans sandbox, le modèle cherche quand même à exécuter du code. Il tombe sur un outil qui n'existe pas, puis il invente un nombre et un hash plausibles, présentés comme « la réponse exacte ». Avec la sandbox, il calcule et les deux réponses sont justes. Il va aussi plus vite : 2 appels au lieu de 3 ou 4.

Tests : `tests/test_run_tool.py`.
