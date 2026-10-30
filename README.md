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

## Fonctionnalités

Chaque fonctionnalité a sa fiche dans [docs/feature/](docs/feature/) : ce qu'elle fait et comment s'en servir.

**Base**
- [B1 · Chatbot en ligne de commande](docs/feature/base/B1-cli-chatbot.md)

**Mémoire et contexte**
- [M1 · Sessions persistantes et profils](docs/feature/memory/M1-sessions-profils.md)

**Outils**
- [T1 · Appel d'outils (MCP)](docs/feature/tools/T1-appel-outils.md)
- [T1 · Serveurs MCP : client et serveur](docs/feature/tools/T1-serveurs-mcp.md)
- [T2 · Exécution de code isolée (sandbox)](docs/feature/tools/T2-sandbox.md)
- [T3 · Recherche web](docs/feature/tools/T3-recherche-web.md)
- [T4 · Accès aux fichiers avec permissions](docs/feature/tools/T4-acces-fichiers.md)
- [T5 · Réponses structurées (JSON)](docs/feature/tools/T5-sortie-structuree.md)

**RAG**
- [R1 · RAG de base](docs/feature/rag/R1-rag-basique.md)
- [R2 · RAG avancé](docs/feature/rag/R2-rag-avance.md)

**Orchestration et raisonnement**
- [A1 · Raisonnement pas à pas (ReAct)](docs/feature/orchestration/A1-react.md)
- [A3 · Plan avant d'agir (human in the loop)](docs/feature/orchestration/A3-human-in-the-loop.md)
- [A6 · Cache sémantique](docs/feature/orchestration/A6-cache-semantique.md)

**Évaluation**
- [EV1 · Évaluation automatique et détection d'hallucinations](docs/feature/evaluation/EV1-eval-hallucinations.md)
- [EV2 · Garde-fous de contenu et de vie privée](docs/feature/evaluation/EV2-garde-fous.md)
- [EV3 · Logs et tableau de bord](docs/feature/evaluation/EV3-monitoring.md)

**Interface et cycle de vie**
- [X1 · Interface web](docs/feature/ux/X1-web-ui.md)
- [X3 · Export et publication](docs/feature/ux/X3-export-publication.md)

Pour aller plus loin : [docs/RAG.md](docs/RAG.md), [docs/CACHE.md](docs/CACHE.md), [docs/EVAL.md](docs/EVAL.md), [docs/MCP.md](docs/MCP.md) et le guide [docs/MCP_GUIDE.md](docs/MCP_GUIDE.md).

## Notes

- Le script d'installation vérifie automatiquement la version de Python (au moins Python 3.12).
- Il installe également Ollma si nécessaire, car le modèle de langage utilisé dépend de ce dernier.
- L'installation peut être désinstallée avec `./install.sh --uninstall`.
