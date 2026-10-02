# Louis

Louis est un assistant basé sur un modèle de langage, qui permet à l'utilisateur de communiquer avec un système d'IA. Il utilise un environnement virtuel Python, un système de gestion de sessions et des outils de logging pour fonctionner.

## Comment le projet marche

- **Environnement virtuel** : Le projet crée un environnement virtuel Python (venv) pour isoler les dépendances.
- **Système de sessions** : Les sessions sont stockées dans une base de données SQLite, et les utilisateurs peuvent avoir des sessions personnalisées.
- **Interface** : L'utilisateur peut interagir avec le système via une interface en ligne de commande (CLI), ou via une interface curses pour un affichage plus avancé.
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

## Base de connaissances (RAG)

Louis cherche dans la documentation et les exemples de code que tu lui indexes (`/index <dossier>`, ou `louis --index <dossier>`) avec l'outil `search_knowledge`, par mots-clés et par le sens (`ollama pull nomic-embed-text`). Le fonctionnement, le garde-fou qui filtre ce que la base rend, et **où trouver de gros jeux de données de code** sont dans [docs/RAG.md](docs/RAG.md).

## Exécution de code (sandbox)

Louis peut tester du code (`python` ou `sh`) avec l'outil `run_code`, après que tu as lu le code et l'as autorisé. Il tourne dans un conteneur Docker sans réseau, sans accès au projet, avec un disque en lecture seule (sauf un petit `/tmp`), limité en temps (10 s), en mémoire (256 Mo) et en processus. Sans Docker, l'outil n'est pas proposé. Les images ne sont jamais téléchargées par Louis : `docker pull python:3.13-alpine alpine:latest`. Les réglages sont les `sandbox.*` de `src/config/settings.py`.

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

## Notes

- Le script d'installation vérifie automatiquement la version de Python (au moins Python 3.12).
- Il installe également Ollma si nécessaire, car le modèle de langage utilisé dépend de ce dernier.
- L'installation peut être désinstallée avec `./install.sh --uninstall`.
