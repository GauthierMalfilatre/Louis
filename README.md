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

Pour aller plus loin : [docs/RAG.md](docs/RAG.md), [docs/CACHE.md](docs/CACHE.md), [docs/EVAL.md](docs/EVAL.md).

## Serveurs MCP

Louis est un **client MCP** ([Model Context Protocol](https://modelcontextprotocol.io)) : il lance au démarrage les serveurs MCP déclarés, leur demande leurs outils, et les donne au modèle avec les siens, sous le nom `<serveur>__<outil>` (`time__get_current_time`). Quand le modèle en appelle un, Louis transmet l'appel au serveur (`tools/call`) et rend le résultat au modèle, qui continue sa réponse avec. Les prompts d'un serveur deviennent des commandes, `/<serveur>:<prompt>`. Louis est aussi un **serveur MCP** : `louis --mcp-server` donne ses outils de lecture à un autre client (voir plus bas).

Deux serveurs sont déclarés par défaut :

- **`calc`**, le serveur de Louis (`src/tool/mcp/servers/calc.py`) : une calculatrice exacte, `calc__calculate`, et un prompt, `/calc:explain <expression>`. Il marche partout, sans rien installer.
- **`time`**, un serveur existant ([mcp-server-time](https://pypi.org/project/mcp-server-time/)) : l'heure dans un fuseau, la conversion entre fuseaux. Il est lancé par `uvx`, qu'on installe avec `pip install uv` (ou `curl -LsSf https://astral.sh/uv/install.sh | sh`).

### Ajouter un serveur

Dans un fichier `.mcp.json`, au **format de Claude Code, Cursor et Claude Desktop** : un fichier de l'un d'eux se copie tel quel.

- `.mcp.json` à la racine du projet : les serveurs de ce projet ;
- `~/.config/louis/mcp.json` : les tiens, pour tous les projets.

```json
{
  "mcpServers": {
    "fs": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/moi/notes"],
      "exclude": ["write_*", "move_file"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"},
      "tools": ["search_*", "get_*"]
    },
    "docs": {
      "type": "http",
      "url": "https://mcp.example.com/mcp",
      "headers": {"Authorization": "Bearer ${DOCS_TOKEN}"}
    },
    "lourd": {"command": "uvx", "args": ["un-serveur-lent"], "enabled": false}
  }
}
```

| Clé       | Ce qu'elle dit |
| --------- | -------------- |
| `command`, `args` | le programme à lancer (`uvx`, `npx`, `python`, un chemin…) et ses arguments, dans le dossier courant |
| `env`     | ses variables d'environnement. Il ne reçoit de celles de Louis que `PATH`, `HOME`, `LANG`… : jamais tes jetons ni tes clés, sauf ceux que tu lui donnes ici |
| `type`, `url`, `headers` | un serveur qui tourne ailleurs, en Streamable HTTP (`type` vaut `http` ; avec une `url` seule, c'est implicite) : son adresse, et les en-têtes de chaque message (un jeton…). L'ancien transport `sse` n'est pas pris en charge |
| `risk`    | `safe`, `reversible` ou `irreversible` pour tous ses outils, ou un niveau par outil, par son nom sur le serveur avec `*` : `{"read_*": "safe", "*": "irreversible"}` (le premier nom qui correspond). Sinon, ce que le serveur dit de chacun |
| `timeout` | les secondes qu'un appel de ses outils peut prendre, à la place de `mcp.timeout` (30) : un serveur lent en demande plus |
| `tools`, `exclude` | les outils proposés au modèle (tous sans `tools`), et ceux qu'on retire, par leur nom sur le serveur, avec `*` (`"write_*"`). Un petit modèle choisit mieux parmi moins d'outils |
| `enabled` | `false` : déclaré, mais pas lancé avec Louis (`/mcp restart <nom>` le lance) |

`${VAR}`, ou `${VAR:-défaut}`, dans `command`, `args`, `env`, `url` et `headers`, est la variable d'environnement de Louis : un jeton se nomme dans le fichier, il n'y est jamais écrit. Une variable absente, sans défaut, laisse ce serveur de côté (`/mcp` dit laquelle). Un serveur d'un fichier remplace celui du même nom déclaré avant lui : les réglages (`mcp.servers`), puis `~/.config/louis/mcp.json`, puis le `.mcp.json` du projet.

Les réglages gardent leur liste, `mcp.servers` dans `src/config/settings.py`, avec les mêmes clés plus `name` : c'est là que sont `calc` et `time`.

**Un serveur du projet attend ton accord.** Un `.mcp.json` vient avec le projet : quiconque y a écrit peut y avoir déclaré une commande. Ses serveurs ne sont lancés qu'une fois approuvés par `/mcp trust <nom>`, après avoir lu leur commande dans `/mcp`. L'accord est gardé hors de tout projet (`~/.config/louis/mcp-trusted.json`), pour ce dossier et cette déclaration : une commande changée demande un nouvel accord.

### `/mcp`

```
> /mcp
Serveurs MCP (3) :
  calc         actif            […/src/tool/mcp/servers/calc.py]
    calc__calculate                  sans risque  Calcule exactement une expression mathématique et renvoie son résulta…
    /calc:explain <expression>                    Calcule une expression avec la calculatrice, puis explique le résulta…
  time         n'a pas démarré  [uvx mcp-server-time]
    la commande uvx est introuvable
  everything   attend ton accord [npx -y @modelcontextprotocol/server-everything]
    déclaré par .mcp.json, un fichier du projet : /mcp trust everything pour l'approuver et le lancer
```

| Commande | Ce qu'elle fait |
| -------- | --------------- |
| `/mcp` | les serveurs, leur état (`actif`, `n'a pas démarré`, `s'est arrêté`, `arrêté`, `désactivé`, `attend ton accord`) avec la raison, leurs outils avec leur risque, leurs prompts |
| `/mcp restart <nom>` | relance un serveur (planté, arrêté, désactivé, qui n'avait pas démarré) : ses outils sont de nouveau proposés |
| `/mcp stop <nom>` | l'arrête : ses outils ne sont plus proposés au modèle |
| `/mcp trust <nom>` | approuve un serveur du projet, et le lance ; ou accepte la nouvelle version de ses outils modifiés |
| `/<serveur>:<prompt> …` | un prompt du serveur, écrit par lui avec tes arguments, puis envoyé au modèle comme ton message. Un seul argument : tout le texte. Plusieurs : dans l'ordre, ou `nom=valeur` (entre guillemets pour les espaces) |

### Ce que Louis garantit

- **Un serveur qui ne démarre pas** (commande introuvable, adresse qui ne répond pas, erreur au lancement, pas de réponse en `mcp.start_timeout` secondes) est noté dans `louis.log` et laissé de côté : Louis démarre sans lui.
- **Une erreur du serveur, un appel trop long** (`mcp.timeout` secondes) **ou un serveur qui plante** donnent au modèle un résultat `Erreur : …`, jamais un plantage de Louis.
- **Un serveur qui a planté est relancé** au prochain appel d'un de ses outils, `mcp.restarts` fois (1 par défaut). L'appel qui l'a vu planter n'est jamais refait : il a peut-être agi. Une session HTTP que le serveur a oubliée est rouverte de la même façon.
- **Un appel long** dont le serveur dit où il en est (`notifications/progress`) s'affiche (`… 2/5 — Téléchargement`), et attend `mcp.timeout` secondes de plus à chaque étape, `mcp.max_timeout` (600) en tout.
- **Les outils et les prompts qui changent** (`list_changed`) sont relus avant ton message suivant : le modèle a les nouveaux, sans relancer Louis.
- **Un outil qui change après que tu l'as vu est retenu.** Le modèle lit la description d'un outil comme une consigne : un serveur ne peut pas la changer dans ton dos. Un outil dont la description, les paramètres ou les annotations ne sont plus ceux de sa première liste n'est plus proposé au modèle, ni dans son ancienne version ni dans la nouvelle, même après une relance. `/mcp` le montre, `/mcp trust <nom>` accepte sa nouvelle version.
- **Les journaux d'un serveur** (`notifications/message`, à partir de `mcp.log_level`) vont dans `louis.log`, jamais à l'écran.
- **Les permissions et le plan** : un outil qui dit ne faire que lire (`readOnlyHint`) ne demande rien. Les autres demandent ton accord avant d'agir. Un outil qui ne dit pas qu'il ne détruit rien est traité comme **irréversible** et passe par le plan (`/plan`).
- **Les serveurs sont arrêtés** quand Louis se ferme, même s'il plante : aucun processus ne reste derrière, une session HTTP est fermée.
- Avec le garde-fou, ce qu'un serveur renvoie passe par les rails des résultats d'outils, et un prompt par ceux des messages, comme ce que tu écris.

### Louis comme serveur MCP

`louis --mcp-server` (ou `python src/main.py --mcp-server`) fait de Louis un serveur MCP sur son entrée et sa sortie standard. Un autre client (Claude Code, Claude Desktop, MCP Inspector, un autre Louis…) le lance dans un projet et reçoit ses outils **qui ne font que lire** : `tree`, `cat_file` et `search`, gardés dans le dossier du projet, et `search_knowledge` dès que quelque chose est indexé (`louis --index`). Rien qui écrive, ni qui sorte de la machine.

```bash
claude mcp add louis -- /chemin/vers/sensai/venv/bin/python /chemin/vers/sensai/src/main.py --mcp-server
npx @modelcontextprotocol/inspector --cli venv/bin/python src/main.py --mcp-server --method tools/list
```

Le fonctionnement en détail (le protocole, les fichiers, les choix) est dans [docs/MCP.md](docs/MCP.md). Pour apprendre MCP et ajouter un serveur pas à pas : [docs/MCP_GUIDE.md](docs/MCP_GUIDE.md).

## Notes

- Le script d'installation vérifie automatiquement la version de Python (au moins Python 3.12).
- Il installe également Ollma si nécessaire, car le modèle de langage utilisé dépend de ce dernier.
- L'installation peut être désinstallée avec `./install.sh --uninstall`.
