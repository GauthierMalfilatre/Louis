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

## Mesure réelle : avec et sans

`qwen3.5:9b` sur le processeur (pas de GPU), `chat.context` à 12 288 (avec les 24 576 par défaut, Ollama manquait de mémoire). « À froid », c'est une nouvelle session : le modèle relit les ~3 800 tokens du prompt et des outils. Ici ça a pris 4 à 5 min, parce que la machine swappait. « À chaud », c'est la question suivante de la même session.

**Streaming** (`chat.stream`). On regarde le délai avant le premier mot affiché. La question à froid est « Explique en trois phrases ce qu'est une closure en Python », la suite à chaud est « Donne un exemple de closure en cinq lignes ».

| | Sans streaming | Avec streaming |
| - | - | - |
| À froid : premier texte affiché | 310,6 s | 284,2 s |
| À froid : réponse complète | 310,7 s | 309,4 s |
| À chaud : premier texte affiché | 21,7 s | **11,2 s** |
| À chaud : réponse complète | 21,7 s | 25,0 s |

Le streaming ne rend pas le modèle plus rapide : la réponse complète arrive au même moment, à ±3 s près. Par contre, on lit dès le premier token au lieu d'attendre la fin. À chaud, l'attente avant le premier mot est divisée par deux. À froid, on ne gagne que 26 s, parce que presque tout le temps passe à lire le prompt, avant le premier token.

**Historique**. On regarde la justesse. Le message d'avant était « Je m'appelle Ada et je code surtout en Rust », puis on demande « Dans quel langage je code surtout ? ».

| | Avec l'historique (même session) | Sans (nouvelle session) |
| - | - | - |
| Réponse | « Rust » ✓ | « Python » ✗ |
| Temps | 4,7 s | 346,5 s |

Sans historique, le modèle répond au hasard le langage le plus courant. Avec, il a juste, et il répond aussi bien plus vite : la requête prolonge la précédente, donc Ollama ne relit pas le prompt.

Tests : `tests/test_chat.py`.
