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
| `llm`    | une requête au modèle : à quoi elle sert (`purpose` : `reply`, `structured`, `check`, `summary`), ce qu'on lui donne, sa réponse, les outils demandés, la latence, le temps jusqu'au premier token, les tokens (prompt / réponse), le temps de chargement, le statut (`ok`, `error`, `cancelled`) |
| `tool`   | un appel d'outil : arguments, succès, durée, début du résultat, et le temps passé à attendre ta permission (`waited`) |
| `guard`  | un rail du garde-fou a modifié un message |
| `rag`    | une recherche dans la base de connaissances : la requête, le mode (`hybrid` ou `keyword`), les passages trouvés, la durée |
| `step`   | une étape du raisonnement pas à pas (`/react`) : ce que le modèle pensait, les outils qu'il a appelés |
| `check`  | la vérification d'un brouillon du raisonnement pas à pas : s'il est passé, ses problèmes, s'il a été réécrit |
| `plan`   | un plan montré avant une action risquée (`/plan`) : ses actions et leur risque, s'il a été approuvé, ce que tu as répondu, le temps que tu as pris pour décider (`waited`) |
| `turn`   | une réponse complète à un message : comment elle s'est terminée, le temps total, dont l'attente de tes permissions (`waited`), les tokens, le nombre de tours ; en pas à pas, les étapes, les vérifications, les brouillons réécrits ; les plans montrés, et ceux refusés |

Les lignes d'un même tour partagent son `turn`. Le temps que tu mets à répondre à une demande de permission est retiré des latences du tableau de bord. Les textes longs sont coupés, et masqués comme dans `louis.log` quand le garde-fou est actif.

Pour voir les métriques (volume d'appels, latence, taux d'erreur, tokens, dérive dans le temps) :

```bash
louis --dashboard                  # ou : python src/main.py --dashboard
cd src && python -m monitor ../louis.traces.jsonl -o /tmp/dashboard.html --open
```

Le résumé s'affiche dans le terminal, et `louis.dashboard.html` (une page autonome, sans serveur) s'ouvre dans le navigateur. En haut, les **dérives** : chaque nouveau prompt ou modèle est comparé à celui qu'il remplace, et les dernières 24 h à la semaine d'avant. Une alerte apparaît au-delà de ±30 % de latence médiane, ±30 % de tokens par appel ou ±5 points de taux d'erreur, avec au moins 5 appels de chaque côté. Un prompt modifié hier qui double la latence apparaît donc en tête, avec la hausse des tokens qui l'explique.

## Évaluation des réponses (LLM juge)

Un modèle relit chaque réponse de Louis, en arrière-plan une fois le tour fini, et la note : **fidélité aux sources** (la réponse découpée en affirmations, chacune vérifiée contre ce que les outils ont lu), **pertinence** et **cohérence** (de 1 à 5). Les affirmations contredites ou invérifiables sont signalées. `/eval` montre les notes de la dernière réponse, `louis --dashboard` les moyennes par prompt et par modèle, et `python -m eval.bench` compare deux versions de Louis sur un jeu de questions fixe avant de livrer. Le détail, les choix et les réglages (`eval.*`) sont dans [docs/EVAL.md](docs/EVAL.md).

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

## Raisonnement pas à pas (ReAct)

Louis peut répondre **pas à pas**, en rendant son raisonnement visible et vérifiable : utile quand la façon d'arriver à la réponse compte autant que la réponse.

- **Chaque étape est dite** : avant chaque action, le modèle écrit ce qu'il sait, ce qui lui manque et ce qu'il va faire, puis lit le résultat de ses outils avant l'étape suivante.
- **La réponse est vérifiée avant d'être donnée** : un fichier qu'elle cite sans qu'aucun outil l'ait lu la fait refuser tout de suite ; sinon le modèle reprend chacune de ses affirmations avec sa source (le résultat d'un outil, un calcul refait) et conclut. Une réponse refusée est réécrite avec ses problèmes (`reason.attempts` fois au plus) ; la dernière est donnée quoi qu'il arrive, avec ce qui reste à redire.
- **Tu ne vois que la réponse vérifiée.** Les brouillons refusés restent dans la session, comme trace, mais pas dans `/export`, `/share` ni `/resume`.

```
> /react
> Quels champs a la classe Reply, et lequel dit si la réponse a été coupée ?
  ⟳ Étape 1 : Je dois trouver où est définie la classe Reply.
  ● Recherche « class Reply »
    ⎿ 1 résultat
  ⟳ Étape 2 : Elle est dans model/reply.py : je le lis pour voir ses champs.
  ● Lecture model/reply.py
    ⎿ 33 lignes lues
  ⟳ Étape 3 : réponse écrite
  ✔ Réponse vérifiée
…
```

`/react` l'active et le coupe (le bouton « Pas à pas » de l'interface web), `louis --react` démarre avec, comme le réglage `reason.enabled`. `reason.verify` coupe la vérification. C'est **plus lent** : chaque vérification est une requête de plus au modèle, d'une à plusieurs minutes sur un processeur sans carte graphique. Il est indépendant de `/think`, qui fait réfléchir le modèle avant chaque réponse dans les deux modes. Le tableau de bord montre la part des réponses justes du premier coup, réécrites, ou données avec des problèmes, et le temps d'une vérification.

## Plan avant d'agir (human in the loop)

Avant une action **qu'on ne peut pas défaire**, Louis s'arrête, te montre son plan, et n'agit qu'après ton accord. Une réponse du modèle qui contient une telle action est suspendue **avant son premier appel** : tu vois ce que Louis veut faire, puis chacune de ses actions dans l'ordre, avec son risque, ce qu'elle fera, comment l'annuler, et ce qu'elle changera (le diff, les commits poussés…).

```
Mon plan : je commite le README, puis je pousse la branche.
  1. Git action=commit message=docs: describe the project · réversible
     un commit sur docs/readme · annulable : git reset --soft HEAD~1 (les changements restent)
  2. Git action=push · IRRÉVERSIBLE
     les commits de docs/readme seront sur origin, visibles par toute l'équipe
a1b2c3d docs: describe the project
Approuver ce plan ? [y] oui  [n] non  [r] répondre
```

- **Oui** : toutes les actions du plan se font, sans autre question.
- **Non** : aucune ne se fait.
- **Répondre** : aucune ne se fait, et ce que tu écris (« fais d'abord une branche ») est donné au modèle, qui propose autre chose.

Sont irréversibles : `git push`, la suppression d'une branche, ouvrir, commenter ou fusionner une pull request, et remplacer ou modifier un fichier dont git n'a pas le contenu actuel (jamais commité, ou changé depuis). Un fichier commité tel quel se restaure avec `git restore` : c'est réversible, comme un commit, une branche ou un nouveau fichier. Une réponse sans action irréversible ne montre pas de plan : chaque outil demande ton accord comme avant. Et un « toujours » donné à un outil ne laisse jamais passer une de ses actions irréversibles : elle est redemandée chaque fois.

`/plan` dit ce qui est réglé, `/plan off` et `/plan on` coupent et remettent les plans, `/plan reversible` les montre pour toute modification, `/plan irreversible` (par défaut) seulement pour ce qui ne s'annule pas. Les réglages sont `hitl.enabled` et `hitl.level`. Un plan auquel personne ne répond (un script, `louis --ask`) est refusé : rien d'irréversible ne se fait sans quelqu'un pour l'approuver. Le tableau de bord montre la part des plans approuvés, refusés ou laissés sans réponse, et le temps pris pour décider.

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
