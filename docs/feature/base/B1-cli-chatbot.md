# B1 · Chatbot en ligne de commande

Louis discute avec un modèle local d'Ollama (`qwen3.5:9b` par défaut, `chat.model.*`) depuis le terminal. La réponse s'affiche au fil de l'eau, et toute la conversation de la session est renvoyée au modèle à chaque message.

## Ce qu'il fait

- **Streaming** : chaque morceau de la réponse s'affiche dès qu'Ollama l'envoie (`chat.stream`). Un appel d'outil écrit en texte par un petit modèle (`<tool_call>{...}`) est reconnu et jamais montré.
- **Historique** : les messages de la session (prompt système, questions, réponses, résultats d'outils) sont envoyés à chaque tour. Quand le contexte (`chat.context`) se remplit, les vieux résultats d'outils sont raccourcis, puis les plus vieux échanges résumés par le modèle (`chat.compact.summary`) au lieu d'être coupés.
- **Deux affichages** : une fenêtre curses (édition de la ligne, défilement, PageUp/PageDown) dans un vrai terminal, du texte simple avec `--plain` ou quand la sortie est redirigée. Les réponses Markdown sont mises en forme.
- **Commandes** : un message qui commence par `/` est une commande, avec son menu. Un chemin (`/src/main.py, que fait ce fichier ?`) reste un message. Une commande inconnue liste celles qui existent.
- **Ctrl+C** arrête la réponse en cours ; Ctrl+D (ou Ctrl+C à l'invite) quitte Louis.
- Un modèle injoignable ou une erreur d'Ollama termine le tour avec son message, sans arrêter Louis.

## Commandes

| Commande | Comment ça marche | À quoi ça sert |
| -------- | ----------------- | -------------- |
| `./install.sh` | crée le venv, installe les dépendances et Ollama, met le lanceur `louis` dans `~/.local/bin` ; `--uninstall` l'enlève | installer Louis une fois |
| `louis` (ou `python src/main.py`) | ouvre la fenêtre curses dans un terminal, du texte simple sinon | discuter avec Louis dans le projet courant |
| `louis --plain` | texte simple, sans curses | un terminal limité, ou copier la sortie |
| `louis --prompt "<texte>"` | remplace le prompt système de Louis | changer son rôle (« tu es un tuteur de maths ») |
| `/` | ouvre le menu des commandes ; une commande inconnue les liste toutes | voir ce que Louis sait faire |
| `/think` | bascule la réflexion du modèle avant chaque réponse (si le modèle sait le faire) | les problèmes durs : plus lent, plus juste |
| `/clear [prompt]` | nouvelle session, avec ce prompt système s'il est donné | repartir de zéro, vider le contexte |
| Ctrl+C / Ctrl+D | arrête la réponse en cours / quitte Louis | reprendre la main |

## Exemples

```bash
./install.sh             # venv, dépendances, Ollama, lanceur `louis`
louis                    # fenêtre curses
louis --plain            # texte simple
louis --prompt "Tu es un tuteur de maths."
```

```
> Salut, tu peux m'expliquer ce que fait src/main.py ?
  ● Lecture src/main.py
    ⎿ 169 lignes lues
Ce fichier est le point d'entrée de Louis : …
> /think                 # le modèle réfléchit avant de répondre (plus lent)
> /clear                 # nouvelle session
```

Tests : `tests/test_chat.py`.
