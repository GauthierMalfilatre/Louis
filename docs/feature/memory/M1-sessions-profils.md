# M1 · Sessions persistantes et profils

Avec `--user <nom>`, chaque conversation est enregistrée dans SQLite (`louis.db`, ou `~/.local/share/louis/` avec le lanceur ; `LOUIS_DB` change le chemin) et se reprend plus tard. Sans `--user`, l'utilisateur est `Anonymous` : rien n'est écrit sur le disque.

## Ce qu'il fait

- **Enregistrement** : une session est écrite à son premier message de l'utilisateur, puis message par message (questions, réponses, appels d'outils et leurs résultats). Une conversation où l'utilisateur n'a rien dit n'est jamais gardée.
- **Profil** : le nom de l'utilisateur et la date sont ajoutés après le prompt système de chaque session. Le prompt système lui-même se change au lancement (`--prompt`) ou par session (`/clear <prompt>`, le champ « Prompt système » de la page web).
- **Reprendre** : `/sessions` liste les sessions (titre, résumé, dossier), `/resume <id>` en reprend une là où elle s'était arrêtée, dans le dossier où elle a eu lieu.
- **Le scribe** : un petit modèle (`scribe.model`, `qwen3:4b-instruct`) écrit le titre et le résumé de chaque session une fois la réponse finie. Il tourne sur le processeur, dans son propre fil, et ne fait jamais attendre Louis. `ollama pull qwen3:4b-instruct` s'il n'est pas déjà là ; `scribe.model: ""` le coupe.
- **Retrouver** : `/find <texte>` (ou la recherche de la barre latérale web) cherche par le sens du titre et du résumé (`nomic-embed-text`), ou par les mots sans lui.
- Plusieurs profils partagent la même base sur une machine, chacun ne voit que ses sessions.

## Commandes

| Commande | Comment ça marche | À quoi ça sert |
| -------- | ----------------- | -------------- |
| `louis --user <nom>` | crée le profil s'il n'existe pas, enregistre ses sessions dans `louis.db` (`LOUIS_DB`) | garder et retrouver ses conversations |
| `/sessions` | liste tes sessions (titre du scribe ou premier message, dossier, `*` pour celle en cours) | voir ce qu'on peut reprendre |
| `/resume <id>` | recharge la session `<id>` et ses messages, si elle a eu lieu dans ce dossier | continuer une conversation là où elle s'était arrêtée |
| `/find <texte>` | cherche par le sens du titre et du résumé (`nomic-embed-text`), sinon par les mots | retrouver une session sans connaître son id |
| `/clear [prompt]` | nouvelle session, sur ce prompt système s'il est donné | changer de sujet ou de consigne |
| `ollama pull qwen3:4b-instruct` | télécharge le modèle du scribe | avoir les titres et les résumés |

## Exemples

```bash
louis --user ada
```

```
> /sessions
Sessions de ada (* : en cours) :
  #12   Jeu du pendu en Python
  #15   Bug de la sauvegarde JSON
* #16   [~/autre-projet] Nouvelle session
> /resume 15
> /find lecture d'un fichier JSON
> /clear Tu réponds toujours en anglais.
```

Tests : `tests/test_session.py`, `tests/test_scribe.py`.
