# Louis

Louis est un assistant basé sur un modèle de langage, qui permet à l'utilisateur de communiquer avec un système d'IA. Il utilise un environnement virtuel Python, un système de gestion de sessions et des outils de logging pour fonctionner.

## Comment le projet marche

- **Environnement virtuel** : Le projet crée un environnement virtuel Python (venv) pour isoler les dépendances.
- **Système de sessions** : Les sessions sont stockées dans une base de données SQLite, et les utilisateurs peuvent avoir des sessions personnalisées.
- **Interface** : L'utilisateur peut interagir avec le système via une interface en ligne de commande (CLI), via une interface curses pour un affichage plus avancé, ou depuis son navigateur (`louis --web`).
- **Modèle de langage** : Le système utilise un modèle de langage (comme Ollama) pour générer des réponses.

## Équipe

- **Gauthier Malfilatre** : Développeur
- **Martin Muller** : Développeur
- **Victor Zhou** : Développeur
- **Julian Hemmer** : Développeur

## Comment le lancer avec Python3 en créant un venv

1. **Créer un venv** :
```bash
python3 -m venv venv
```

2. **Activer le venv** :
```bash
source venv/bin/activate
```

3. **Installer les dépendances** :
```bash
pip install -r requirements.txt
```

4. **Exécuter le projet** :
```bash
python src/main.py
```

## Comment l'installer avec le script bash fourni

1. **Exécuter le script d'installation** :
```bash
./install.sh
```

2. **Le script fait automatiquement** : 
- Créer un environnement virtuel.
- Installer les dépendances.
- Créer un lanceur (`louis`) dans `$HOME/.local/bin`.
- Configurer le PATH pour que `louis` soit accessible depuis n'importe quel répertoire.

## Interface web

```bash
louis --web                  # http://127.0.0.1:8080
louis --web --port 9000 --user ada
```

Louis s'ouvre dans le navigateur au lieu du terminal. Il t'accueille selon l'heure, te propose de reprendre ta dernière session et des idées tirées de ton projet (tes changements en cours dans git). La réponse s'écrit en direct, chaque appel d'outil s'affiche pendant qu'il tourne, puis Louis le résume en une phrase (« J'ai lu calc.py. ») qui se déplie d'un clic, et les permissions se donnent depuis la page, avec le diff de ce que l'outil veut changer (`O` autoriser, `N` refuser, `T` toujours pour cet outil dans la session). Le bouton ■ arrête ce que Louis fait, comme Ctrl+C dans le terminal. Sous chaque réponse : ce qu'elle a coûté (tokens écrits, vitesse, premier token, et le chargement du modèle quand il a été long), et sous chaque recherche dans la base de connaissances, les passages trouvés. Quand l'onglet est caché, son titre et son icône te disent que Louis attend ta réponse ou qu'il a fini ; la cloche y ajoute une notification du bureau. La barre de gauche liste tes sessions (avec `--user`) : un clic en reprend une, « Nouvelle session » fait un `/clear`. Les commandes (`/`) marchent comme dans le terminal, avec leur menu. Ctrl+C dans le terminal arrête Louis.

Le serveur écoute sur `127.0.0.1` : ce poste seulement. `--host 0.0.0.0` l'ouvre au réseau, **sans mot de passe** : qui l'atteint peut faire agir Louis sur tes fichiers.

Il sert aussi les liens publics de `/share` (`/s/<jeton>`) : les liens pointent vers lui tant que `share.base_url` (dans `src/config/settings.py`) est vide, ou vers l'adresse donnée par ce réglage ou par `LOUIS_SHARE_URL` (un proxy, un nom de domaine...).

## Le scribe : titres, résumés, accueil

À côté de la conversation, un petit modèle (`scribe.model`, qwen3:4b-instruct par défaut, le même que `rag.describe.model`) écrit le titre et le résumé de chaque session une fois la réponse finie, et la phrase qui t'accueille sur la page web, d'après ta dernière session et tes changements en cours. Il tourne sur le processeur, dans son propre fil : il ne prend jamais la carte graphique au modèle de la conversation, et Louis ne l'attend jamais. Les sessions d'avant sont décrites quand il n'a rien d'autre à faire.

- **Retrouver une session** : `/find <texte>`, ou la recherche de la barre latérale de `louis --web`, par le sens du titre et du résumé (avec `nomic-embed-text`, le modèle d'embedding du RAG), ou par les mots sans lui.
- **Résumer au lieu de couper** : quand le contexte est plein, les plus vieux échanges qui en sortent sont résumés par le modèle de la conversation (les demandes, ce qu'il a appris des fichiers lus, les réponses déjà données), et il relit ce résumé à leur place. `chat.compact.summary: False` revient à les couper seulement.

`ollama pull qwen3:4b-instruct` s'il n'est pas déjà là ; `scribe.model: ""` coupe le scribe.

## Base de connaissances (RAG)

Louis cherche dans la documentation et les exemples de code que tu lui indexes (`/index <dossier>`, ou `louis --index <dossier>`) avec l'outil `search_knowledge`, par mots-clés et par le sens (`ollama pull nomic-embed-text`). Le fonctionnement, le garde-fou qui filtre ce que la base rend, et **où trouver de gros jeux de données de code** sont dans [docs/RAG.md](docs/RAG.md).

## Exécution de code (sandbox)

Louis peut tester du code (`python`, `sh`, `c`, `cpp`, `go` ou `rust`, bibliothèque standard seulement) avec l'outil `run_code`, après que tu as lu le code et l'as autorisé. Il tourne dans un conteneur Docker sans réseau, sans accès au projet, avec un disque en lecture seule (sauf un petit `/tmp`), limité en temps (10 s, 30 s pour c et c++, une minute pour go et rust, compilation comprise), en mémoire et en processus. Sans Docker, l'outil n'est pas proposé. Les images ne sont jamais téléchargées par Louis : `docker pull python:3.13-alpine alpine:latest golang:alpine rust:alpine gcc:latest` (2 Go pour gcc : `sandbox.languages` permet d'en indiquer une plus légère). Les réglages sont les `sandbox.*` de `src/config/settings.py`.

## Monitoring

Chaque appel au modèle et aux outils est enregistré, une ligne JSON par événement, dans `louis.traces.jsonl` (à côté de `louis.db` : dans le dossier courant, ou dans `~/.local/share/louis/` avec le lanceur de `install.sh` ; `LOUIS_TRACES` change le chemin).

| Type     | Ce qu'il contient |
| -------- | ----------------- |
| `run`    | un lancement de Louis : le modèle, les réglages qui jouent sur la vitesse |
| `prompt` | un prompt système, en entier, la première fois qu'il est vu : les autres lignes le nomment par sa version (début de son hash) |
| `llm`    | une requête au modèle : ce qu'on lui donne, sa réponse, les outils demandés, la latence, le temps jusqu'au premier token, les tokens (prompt / réponse), le temps de chargement, le statut (`ok`, `error`, `cancelled`) |
| `tool`   | un appel d'outil : arguments, succès, durée, début du résultat, et le temps passé à attendre ta permission (`waited`) |
| `guard`  | un rail du garde-fou a modifié un message |
| `rag`    | une recherche dans la base de connaissances : la requête, le mode (`hybrid` ou `keyword`), les passages trouvés, la durée |
| `turn`   | une réponse complète à un message : comment elle s'est terminée, le temps total, dont l'attente de tes permissions (`waited`), les tokens, le nombre de tours |

Les lignes d'un même tour partagent son `turn`. Le temps que tu mets à répondre à une demande de permission est retiré des latences du tableau de bord. Les textes longs sont coupés, et masqués comme dans `louis.log` quand le garde-fou est actif.

Pour voir les métriques (volume d'appels, latence, taux d'erreur, tokens, dérive dans le temps) :

```bash
louis --dashboard                  # ou : python src/main.py --dashboard
cd src && python -m monitor ../louis.traces.jsonl -o /tmp/dashboard.html --open
```

Le résumé s'affiche dans le terminal, et `louis.dashboard.html` (une page autonome, sans serveur) s'ouvre dans le navigateur. En haut, les **dérives** : chaque nouveau prompt ou modèle est comparé à celui qu'il remplace, et les dernières 24 h à la semaine d'avant. Une alerte apparaît au-delà de ±30 % de latence médiane, ±30 % de tokens par appel ou ±5 points de taux d'erreur, avec au moins 5 appels de chaque côté. Un prompt modifié hier qui double la latence apparaît donc en tête, avec la hausse des tokens qui l'explique.

## Réponses structurées (JSON)

Louis peut répondre en JSON qui respecte un **schéma JSON** (un formulaire : les champs, leurs types, ceux qui sont obligatoires), au lieu de texte. Ollama empêche le modèle d'écrire autre chose, puis Louis vérifie la réponse et la redemande avec l'erreur si elle ne correspond pas (`structured.attempts` fois au plus). Une réponse qui ne correspond toujours pas n'est jamais renvoyée : c'est une erreur. Dans ce mode, le modèle n'a pas d'outils : ce qu'il doit lire est dans la question.

Les schémas sont cherchés par leur nom dans `schemas/` du dossier courant, puis dans ceux de Louis (`src/structured/schemas/` : `todo`, `resume`, `contact`). On peut aussi donner le chemin d'un fichier.

Dans la conversation :

```
> /schemas
> /json contact Gauthier Malfilatre, développeur chez Sensai, gauthier.m@sensai.dev
{
  "nom": "Gauthier Malfilatre",
  "entreprise": "Sensai",
  "poste": "développeur",
  "email": "gauthier.m@sensai.dev",
  "telephone": null
}
```

Depuis un script : la sortie est **seulement** le JSON, le texte envoyé par un pipe est ajouté à la question, les erreurs vont sur stderr.

```bash
cat compte-rendu.txt | louis --schema todo --ask "Extrais les tâches" > taches.json
louis --schema ./mon_schema.json --ask "..." | jq '.champ'
```

Code de retour : `0` réponse valide, `1` réponse invalide ou modèle injoignable, `2` schéma introuvable ou invalide. Le tableau de bord (`louis --dashboard`) montre la part des réponses valides, et celles valides du premier coup.

## Notes

- Le script d'installation vérifie automatiquement la version de Python (au moins Python 3.12).
- Il installe également Ollma si nécessaire, car le modèle de langage utilisé dépend de ce dernier.
- L'installation peut être désinstallée avec `./install.sh --uninstall`.
