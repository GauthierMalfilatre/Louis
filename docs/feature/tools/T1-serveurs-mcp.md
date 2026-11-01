# T1 · Serveurs MCP

Louis est un **client MCP** ([Model Context Protocol](https://modelcontextprotocol.io)) : il lance au démarrage les serveurs MCP déclarés, leur demande leurs outils, et les donne au modèle avec les siens, sous le nom `<serveur>__<outil>` (`time__get_current_time`). Quand le modèle en appelle un, Louis transmet l'appel au serveur (`tools/call`) et rend le résultat au modèle, qui continue sa réponse avec. Les prompts d'un serveur deviennent des commandes, `/<serveur>:<prompt>`. Louis est aussi un **serveur MCP** : `louis --mcp-server` donne ses outils de lecture à un autre client (voir plus bas).

Trois serveurs sont déclarés par défaut :

- **`calc`**, le serveur de Louis (`src/tool/mcp/servers/calc.py`) : une calculatrice exacte, `calc__calculate`, et un prompt, `/calc:explain <expression>`. Il marche partout, sans rien installer.
- **`time`**, un serveur existant ([mcp-server-time](https://pypi.org/project/mcp-server-time/)) : l'heure dans un fuseau, la conversion entre fuseaux. Il est lancé par `uvx`, qu'on installe avec `pip install uv` (ou `curl -LsSf https://astral.sh/uv/install.sh | sh`).
- **`github`**, le serveur officiel de GitHub ([github-mcp-server](https://github.com/github/github-mcp-server)), réduit à ses outils d'issues, et parmi eux aux trois dont le modèle a besoin : `github__list_issues`, `github__search_issues` et `github__issue_write`. Il est lancé par Docker et prend le jeton de ton compte GitHub dans `gh`, comme les outils de pull request : connecte-toi une fois avec `gh auth login`, il n'y a rien d'autre à faire (`GITHUB_TOKEN`, s'il est défini, passe avant). Sans `gh` ou sans connexion, il ne démarre pas, `/mcp` dit pourquoi, et Louis continue sans lui (voir [la démo](#démo--ouvrir-une-issue-github)).

## Ajouter un serveur

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
| `env_from` | ses variables d'environnement données par ce qu'une commande affiche, pour celles que `env` ne donne pas : `{"GITHUB_PERSONAL_ACCESS_TOKEN": ["gh", "auth", "token"]}`. La commande est lancée à chaque démarrage du serveur (donc jamais avant `/mcp trust`), et ce qu'elle affiche n'est jamais écrit dans les journaux. Si elle échoue, le serveur ne démarre pas, et `/mcp` dit pourquoi. Seulement pour un serveur lancé par Louis (stdio) |
| `type`, `url`, `headers` | un serveur qui tourne ailleurs, en Streamable HTTP (`type` vaut `http` ; avec une `url` seule, c'est implicite) : son adresse, et les en-têtes de chaque message (un jeton…). L'ancien transport `sse` n'est pas pris en charge |
| `risk`    | `safe`, `reversible` ou `irreversible` pour tous ses outils, ou un niveau par outil, par son nom sur le serveur avec `*` : `{"read_*": "safe", "*": "irreversible"}` (le premier nom qui correspond). Sinon, ce que le serveur dit de chacun |
| `timeout` | les secondes qu'un appel de ses outils peut prendre, à la place de `mcp.timeout` (30) : un serveur lent en demande plus |
| `tools`, `exclude` | les outils proposés au modèle (tous sans `tools`), et ceux qu'on retire, par leur nom sur le serveur, avec `*` (`"write_*"`). Un petit modèle choisit mieux parmi moins d'outils |
| `enabled` | `false` : déclaré, mais pas lancé avec Louis (`/mcp restart <nom>` le lance) |

`${VAR}`, ou `${VAR:-défaut}`, dans `command`, `args`, `env`, `url` et `headers`, est la variable d'environnement de Louis : un jeton se nomme dans le fichier, il n'y est jamais écrit. Une variable absente, sans défaut, laisse ce serveur de côté (`/mcp` dit laquelle). Un serveur d'un fichier remplace celui du même nom déclaré avant lui : les réglages (`mcp.servers`), puis `~/.config/louis/mcp.json`, puis le `.mcp.json` du projet.

Les réglages gardent leur liste, `mcp.servers` dans `src/config/settings.py`, avec les mêmes clés plus `name` : c'est là que sont `calc`, `time` et `github`.

**Un serveur du projet attend ton accord.** Un `.mcp.json` vient avec le projet : quiconque y a écrit peut y avoir déclaré une commande. Ses serveurs ne sont lancés qu'une fois approuvés par `/mcp trust <nom>`, après avoir lu leur commande dans `/mcp`. L'accord est gardé hors de tout projet (`~/.config/louis/mcp-trusted.json`), pour ce dossier et cette déclaration : une commande changée demande un nouvel accord.

## `/mcp`

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

## Ce que Louis garantit

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

## Démo : ouvrir une issue GitHub

Le serveur MCP officiel de GitHub ([github-mcp-server](https://github.com/github/github-mcp-server)), lancé par Docker et réduit à ses outils d'issues : Louis lit le code qui dessine le serpent, puis ouvre l'issue pour remplacer son sprite buggé, une fois que tu l'as approuvée.

1. **L'image**, une fois avant la démo : sinon le premier lancement la télécharge, et peut dépasser `mcp.start_timeout`.
   ```bash
   docker pull ghcr.io/github/github-mcp-server
   ```
2. **Le compte GitHub** : une seule fois, avec un compte qui peut écrire sur le repo de la démo. Louis prend ensuite le jeton de `gh` tout seul :
   ```bash
   gh auth login
   ```
   Un repo d'une organisation qui impose le SSO (SAML) demande aussi d'autoriser pour elle la connexion de `gh` : sur github.com, Settings › Applications › GitHub CLI pour une connexion par le navigateur, ou Settings › Developer settings › Tokens › Configure SSO pour un jeton donné à `gh`. Sinon chaque appel rend `Resource protected by organization SAML enforcement`.
3. **Le serveur** est déclaré par défaut, dans `mcp.servers` (`src/config/settings.py`) : rien à écrire. `GITHUB_TOOLSETS=issues` ne fait exposer au serveur que ses outils d'issues (10), et `tools` n'en garde que trois pour le modèle : un petit modèle choisit mieux parmi peu d'outils. Pour en changer, un serveur `github` déclaré dans `~/.config/louis/mcp.json` remplace celui des réglages.
4. **Vérifier**, dans le dossier du Snake : `louis --web`, puis `/mcp`. `github` est `actif`, avec `github__list_issues` et `github__search_issues` `sans risque`, et `github__issue_write` `IRRÉVERSIBLE`.
5. **La demande** : « Le sprite du serpent est buggé : regarde le code qui le dessine, puis crée une issue sur le repo du projet pour le remplacer par un plus beau. » Le repo du projet est celui où Louis tourne : Louis lit son `origin` et donne au modèle son `owner/repo` GitHub, dans le contexte de chaque session. Il faut donc lancer Louis dans le dossier du Snake, cloné depuis GitHub. Louis lit le code, puis appelle `github__issue_write` avec `method: "create"`, `owner`, `repo`, `title` et `body`. L'outil ne dit pas qu'il ne fait que lire, donc Louis s'arrête et montre son plan avec ces paramètres : rien ne part avant ton accord. Une fois le plan approuvé, l'issue est créée et Louis donne son lien.
   S'il n'appelle pas l'outil, la demande de secours le nomme : « Crée l'issue sur le repo du projet avec github__issue_write. »

Avec Docker sans root, ou une autre socket, ajoute `"DOCKER_HOST": "${DOCKER_HOST}"` à son `env` : Louis ne passe au serveur que `PATH`, `HOME`, `LANG`… de son environnement.

## Louis comme serveur MCP

`louis --mcp-server` (ou `python src/main.py --mcp-server`) fait de Louis un serveur MCP sur son entrée et sa sortie standard. Un autre client (Claude Code, Claude Desktop, MCP Inspector, un autre Louis…) le lance dans un projet et reçoit ses outils **qui ne font que lire** : `tree`, `cat_file` et `search`, gardés dans le dossier du projet, et `search_knowledge` dès que quelque chose est indexé (`louis --index`). Rien qui écrive, ni qui sorte de la machine.

```bash
claude mcp add louis -- /chemin/vers/sensai/venv/bin/python /chemin/vers/sensai/src/main.py --mcp-server
npx @modelcontextprotocol/inspector --cli venv/bin/python src/main.py --mcp-server --method tools/list
```

Le fonctionnement en détail (le protocole, les fichiers, les choix) est dans [docs/MCP.md](../../MCP.md). Pour apprendre MCP et ajouter un serveur pas à pas : [docs/MCP_GUIDE.md](../../MCP_GUIDE.md).

Tests : `tests/test_mcp*.py` (101 tests). L'appel d'outils lui-même, côté modèle : [T1 · Appel d'outils](T1-appel-outils.md).
