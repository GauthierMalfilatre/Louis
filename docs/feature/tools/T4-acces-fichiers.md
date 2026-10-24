# T4 · Accès aux fichiers avec permissions

Louis lit, cherche, crée et modifie les fichiers du projet, sans jamais en sortir. Tout ce qui écrit demande d'abord l'accord de l'utilisateur, avec le diff de ce qui va changer.

## Ce qu'il fait

| Outil | Rôle | Demande l'accord |
| ----- | ---- | ---------------- |
| `tree` | arborescence (dossiers d'abord, sans `.git`, `node_modules`, builds…) | non |
| `cat_file` | lit un fichier, lignes numérotées, par tranches de 400 lignes | non |
| `search` | cherche une regex dans les fichiers (`glob`, `(?i)`) | non |
| `write_file` | crée un fichier ; n'en remplace un qu'avec `overwrite` | oui, avec le contenu |
| `edit_file` | remplace un passage exact d'un fichier **déjà lu** | oui, avec le diff |
| `mkdir` | crée un dossier et ses parents | oui |

- **Périmètre** : les chemins partent de la racine du projet (le dossier où Louis est lancé). `../`, un chemin absolu ou un lien qui en sort sont refusés.
- **Lu avant d'écrire** : `edit_file` refuse un fichier que le modèle n'a pas lu, ou qui a changé depuis.
- **Permissions** : `y` oui, `n` non, `a` toujours pour cet outil dans la session. Un refus est dit au modèle, qui ne réessaie pas. Une action irréversible est redemandée à chaque fois, même après « toujours » (voir [A3](../orchestration/A3-human-in-the-loop.md)).
- Les petites erreurs des petits modèles (numéros de ligne recopiés, `\n` échappés) sont réparées par `edit_file`.

## Commandes

| Commande | Comment ça marche | À quoi ça sert |
| -------- | ----------------- | -------------- |
| `y` | autorise cette action, une fois | valider un changement après avoir lu le diff |
| `n` | refuse ; le modèle le lit et ne réessaie pas | empêcher un changement |
| `a` | autorise cet outil pour toute la session (jamais pour une action irréversible) | ne plus répondre à chaque écriture |
| `louis` lancé dans un dossier | ce dossier devient la racine : rien n'est lu ni écrit en dehors | choisir ce que Louis peut toucher |

## Exemple

```
> Renomme la fonction load en load_settings dans config.py
  ● Lecture config.py
  ● Modification config.py
    - def load():
    + def load_settings():
    Autoriser ? [y] oui  [n] non  [a] toujours pour edit_file dans cette session  y
C'est fait.
```

Tests : `tests/test_file_tools.py`, `tests/test_write_tool.py`, `tests/test_edit_tool.py`, `tests/test_permission.py`.
