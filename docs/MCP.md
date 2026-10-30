# Client (et serveur) MCP

> Pour apprendre ce qu'est MCP, comment le code marche pas à pas et comment ajouter un serveur, lis d'abord le guide : [MCP_GUIDE.md](MCP_GUIDE.md) (en anglais). Ce document-ci est le rapport.

Louis sait appeler des outils pendant qu'il répond : le modèle s'interrompt, émet un appel structuré (le nom d'un outil et ses arguments), Louis l'exécute, lui rend le résultat, et le modèle continue sa réponse avec. Au départ, ces outils étaient tous écrits dans Louis (`cat_file`, `git`, `web_search`…).

Cette fonctionnalité fait de Louis un **client MCP** ([Model Context Protocol](https://modelcontextprotocol.io)) : n'importe quel programme qui parle MCP lui apporte ses outils et ses prompts, sans une ligne de code dans Louis. On le déclare dans un fichier `.mcp.json` ou dans les réglages ; Louis le lance (ou le joint à son adresse), lui demande ce qu'il offre, et le donne au modèle avec ses propres outils. Dans l'autre sens, `louis --mcp-server` fait de Louis un **serveur MCP** pour un autre client.

Elle a été faite en deux branches :

- **`feat/mcp-client`** : le sujet (le client stdio, `/mcp`, les erreurs, les permissions, la démo, les tests, le README) ;
- **`feat/mcp-improvements`** : six améliorations, demandées après la démo (relance, progression et journaux, fichiers `.mcp.json`, HTTP, prompts, Louis serveur).

## Ce que fait la fonctionnalité

### Le sujet (`feat/mcp-client`)

| Exigence | Où |
| --- | --- |
| Le modèle appelle un outil, Louis l'exécute, rend le résultat, le modèle continue | inchangé : `App.__call` (`src/app/app.py`) |
| Serveurs déclarés dans les réglages (`mcp.servers` : `name`, `command`, `args`, `env`), en stdio | `src/config/settings.py`, `src/tool/mcp/config.py` |
| Au démarrage, chaque serveur est lancé, ses outils listés et enregistrés sous `<serveur>__<outil>` | `McpManager.start`, `McpServer.start`, `App.offer_mcp` |
| Un appel du modèle passe par `call_tool`, son résultat est rendu au modèle | `McpTool.handle`, `McpClient.call_tool` |
| Erreur MCP, timeout ou serveur planté → résultat `Erreur : …`, jamais un plantage | `McpTool.handle`, `McpClient` |
| Un serveur qui ne démarre pas est noté dans le log et laissé de côté | `McpServer.start` |
| Les outils MCP passent par les permissions et le plan | `McpTool.risk`, `McpTool.handle` |
| Les serveurs sont arrêtés proprement quand Louis se ferme | `App.close`, `McpClient.close`, les transports, `atexit` |
| `/mcp` liste les serveurs, leur état et leurs outils | `src/command/impl/command_mcp.py`, les interfaces |
| Démo avec un serveur existant et un serveur à nous | `time` (mcp-server-time) et `calc` (le nôtre) |
| `tests/test_mcp.py` : outils découverts, appel réussi, appel en échec, serveur qui ne démarre pas | `tests/test_mcp.py`, `tests/mcp_fake_server.py` |
| README : comment ajouter un serveur MCP | `README.md`, section « Serveurs MCP » |

### Les améliorations (`feat/mcp-improvements`)

| Amélioration | Ce qu'elle change | Où |
| --- | --- | --- |
| **Relance et outils vivants** | `/mcp restart` et `/mcp stop` ; un serveur planté est relancé au prochain appel ; un serveur qui change ses outils (`list_changed`) est relu sans relancer Louis | `McpServer.restart/connect/refresh`, `App.offer_mcp`, `App.answer` |
| **Progression et journaux** | un appel long affiche où il en est, et n'est pas coupé tant que le serveur travaille ; les journaux du serveur vont dans `louis.log` | `McpClient.request`, `McpTool`, `MCP_PROGRESS` |
| **`.mcp.json` et filtres** | les serveurs déclarés au format de Claude Code, avec `${VAR}` ; `tools`/`exclude` ; `enabled` ; un serveur du projet attend ton accord (`/mcp trust`) | `src/tool/mcp/config.py` |
| **Transport HTTP** | les serveurs distants, en Streamable HTTP (`url`, `headers`) | `src/tool/mcp/transport_http.py` |
| **Prompts en commandes** | les prompts d'un serveur deviennent `/<serveur>:<prompt>` | `src/command/impl/command_mcp_prompt.py` |
| **Louis serveur MCP** | `louis --mcp-server` donne ses outils de lecture à un autre client | `src/tool/mcp/serve.py` |

## Les fichiers

Tout le code MCP est dans `src/tool/mcp/` : un outil MCP est un outil de Louis comme les autres.

| Fichier | Rôle |
| --- | --- |
| `src/tool/mcp/client.py` | `McpClient` : la session JSON-RPC 2.0 avec un serveur, quel que soit son transport. Les requêtes et leurs réponses, les requêtes du serveur, la progression, les journaux, les listes qui changent. Aucune dépendance. |
| `src/tool/mcp/transport_stdio.py` | `StdioTransport` : le serveur est un programme que Louis lance et à qui il parle sur son entrée et sa sortie standard. |
| `src/tool/mcp/transport_http.py` | `HttpTransport` : le serveur tourne ailleurs, à une adresse (Streamable HTTP). `urllib` seulement. |
| `src/tool/mcp/config.py` | Où sont déclarés les serveurs : les réglages et les fichiers `.mcp.json`, les variables `${VAR}`, la validation, et `Trust`, les serveurs du projet que tu as approuvés. |
| `src/tool/mcp/manager.py` | `McpServer` (un serveur : son état, son démarrage, sa relance, ses outils et ses prompts) et `McpManager` (tous les serveurs, démarrés en parallèle). |
| `src/tool/mcp/tool_mcp.py` | `McpTool` : un outil d'un serveur, vu par le modèle comme un outil de Louis. Son nom, son schéma, son risque, son appel, sa progression, et la conversion du résultat en texte. |
| `src/tool/mcp/servers/calc.py` | `calc`, **notre serveur MCP** : une calculatrice exacte et un prompt, `explain`. Un programme à part, que Louis lance comme n'importe quel serveur. |
| `src/tool/mcp/serve.py` | **Louis serveur MCP** (`--mcp-server`) : ses outils de lecture, offerts à un autre client. |
| `src/command/impl/command_mcp.py` | `/mcp`, `/mcp restart|stop|trust <serveur>`. |
| `src/command/impl/command_mcp_prompt.py` | `/<serveur>:<prompt>` : un prompt d'un serveur, envoyé au modèle. |
| `src/command/command.py` | Un nom de commande peut avoir la forme `serveur:prompt` ; `CommandTree.unregister`. |
| `src/config/settings.py` | `mcp.servers` (`calc` et `time`), `mcp.files`, `mcp.trust_file`, `mcp.timeout`, `mcp.start_timeout`, `mcp.max_timeout`, `mcp.restarts`, `mcp.log_level`. |
| `src/events/event_list.py` | `MCP_STARTED`, `MCP_SERVERS`, `MCP_CHANGED`, `MCP_PROGRESS`, `MCP_PROMPT`. |
| `src/app/app.py` | Démarre les serveurs, `App.offer_mcp` (outils et prompts proposés, toujours dans le même ordre), `App.answer` (relit ce qui a changé avant chaque message), `App.mcp_changed`, `App.close`. Les résultats MCP passent par le garde-fou. |
| `src/tool/tool_manager.py` | `ToolManager.tools()`. |
| `src/main.py` | `app.close()` à la fin de `run()`, même en cas de plantage. `--ask` ne lance aucun serveur. `--mcp-server`. |
| `src/interface/cli.py`, `cli_curses.py`, `web.py` | Ce qui arrive aux serveurs, la progression, les prompts, dans le terminal, la fenêtre curses (qui hérite du CLI) et la page web. |
| `tests/mcp_fake_server.py` | Un faux serveur MCP qui échoue sur commande, change ses outils, dit sa progression, a des journaux et des prompts. |
| `tests/test_mcp*.py` | 93 tests, voir [Tests](#tests). |
| `tests/conftest.py` | Les serveurs et les fixtures MCP partagés ; aucun test ne lance les serveurs des réglages ni ne lit tes fichiers `.mcp.json`. |

### Les commits

Les deux branches suivent `CONTRIBUTING.md` : `verbe: phrase en minuscules.`, un commit par fichier ou par fonctionnalité, et les tests passent après chacun.

**`feat/mcp-client`**, partie de `feat/human-in-the-loop`, car le plan (`Tool.risk`, `tool/risk.py`) n'existe que là :

1. `add: the json-rpc client that talks to an mcp server over stdio.`
2. `add: the mcp tool, a tool of a server offered to the model, with its risk and its permission.`
3. `add: the mcp manager, that starts the servers in parallel, lists their tools and stops them.`
4. `add: calc, the own mcp server of louis, a calculator.`
5. `add: the mcp settings, the servers louis starts and their timeouts.`
6. `add: the mcp events, the servers started and listed.`
7. `add: the mcp servers started with louis, their tools offered to the model, and stopped when it exits.`
8. `add: the results of the mcp tools put through the guard as untrusted.`
9. `add: /mcp, the servers with their state and their tools.`
10. `add: the mcp servers shown in the cli and the curses window.`
11. `add: the mcp servers shown in the web page.`
12. `add: the fake mcp server of the tests, that fails on demand.`
13. `add: the tests of the mcp client: tools, calls, errors, timeouts and servers that do not start.`
14. `add: the readme section on how to add an mcp server.`
15. `add: the report on the mcp client and how it works.`

**`feat/mcp-improvements`**, partie de `feat/mcp-client` :

1. `refactor: the stdio side of the mcp client moved to its own transport.`
2. `add: the restart of an mcp server, and its tools listed again when it says they changed.`
3. `add: the mcp tools offered again after a server restarted or changed them.`
4. `add: /mcp restart and /mcp stop, and the event of a server that changed.`
5. `add: the changes of the mcp servers shown in the cli and the web page.`
6. `add: the tests of the restart of the mcp servers and of their tools that change.`
7. `add: the progress of a long mcp call, its timeout put off while the server works.`
8. `add: the logs of the mcp servers written in louis.log.`
9. `add: the progress of the mcp calls shown in the cli and the web page.`
10. `fix: the seconds an mcp call waited rounded to a tenth.`
11. `add: the tests of the progress and the logs of the mcp servers.`
12. `add: the .mcp.json files, in the format of claude code, with the env variables they name.`
13. `add: the tools of a server filtered, and a server turned off by its settings.`
14. `add: the servers of a project started only once the user trusts them, with /mcp trust.`
15. `add: the tests of the mcp configuration files, the filters and the trust.`
16. `add: the http transport of mcp, for the servers that run elsewhere.`
17. `fix: the stream of an mcp server closed while it is read, without an error in its thread.`
18. `add: the tests of the http transport, against a fake http server.`
19. `add: the prompts of the mcp servers, listed with their tools.`
20. `add: the prompts of the mcp servers run as /server:prompt commands.`
21. `add: explain, a prompt of calc.`
22. `add: the tests of the mcp prompts.`
23. `add: louis as an mcp server, its tools that read offered to other clients.`
24. `fix: the knowledge base of louis as an mcp server read again while it is empty.`
25. `add: the tests of louis as an mcp server.`
26. `fix: the mcp tools always offered in the same order, so ollama goes on from what it read.`
27. `fix: a server that says its tools changed but lists the same ones is no change for the user.`
28. `update: the readme section on mcp: the json files, http, the filters, the prompts and louis as a server.`
29. `update: the report on the mcp client with what it gained.`

Les `fix:` sont des défauts trouvés en chemin, par les tests ou par la démo en direct : un test qui aurait pu échouer au hasard (`0.801 s`), une erreur dans un thread quand Louis ferme un flux HTTP, une base de connaissances indexée pendant que le serveur tourne, et deux comportements vus avec un vrai modèle (plus bas, [L'ordre des outils](#lordre-des-outils)).

## Comment ça marche

### Le protocole

Louis et un serveur s'échangent des messages **JSON-RPC 2.0** :

- en **stdio**, le serveur est un programme que Louis lance : un message par ligne, sur son entrée et sa sortie standard (sa sortie d'erreur est faite pour les logs) ;
- en **HTTP**, chaque message est envoyé (POST) à l'adresse du serveur, qui répond en JSON ou en un flux d'événements (SSE).

Une **requête** a un `id`, une `method` et des `params`. Sa **réponse** reprend le même `id`, avec un `result` ou une `error`. Une **notification** n'a pas d'`id` : on n'y répond pas.

| Sens | Méthodes |
| --- | --- |
| Louis → serveur | `initialize` (accord sur la version), `notifications/initialized`, `tools/list` et `prompts/list` (page par page), `tools/call`, `prompts/get`, `logging/setLevel`, `notifications/cancelled` |
| serveur → Louis, notifications | `notifications/progress` (où en est un appel), `notifications/message` (ses journaux), `notifications/tools/list_changed`, `notifications/prompts/list_changed` |
| serveur → Louis, requêtes | `ping` reçoit `{}`, `roots/list` reçoit le dossier du projet, les autres une erreur `-32601` (méthode inconnue) |

### Du démarrage à la réponse

```
 Louis (App)              McpManager / McpServer / McpClient       serveur MCP
     │                              │                                       │
     │  McpManager(settings)        │  config.py : réglages + .mcp.json,    │
     │                              │  ${VAR}, validation, accord du projet │
     │  .start() ──────────────────►│  un thread par serveur, en parallèle  │
     │                              │  transport.open() ───────────────────►│  lancé (stdio) ou joint (HTTP)
     │                              │──── initialize ──────────────────────►│
     │                              │◄─── protocolVersion, capabilities ────│
     │                              │──── notifications/initialized ───────►│
     │                              │──── logging/setLevel (s'il en a) ────►│
     │                              │──── tools/list, prompts/list ────────►│
     │                              │◄─── outils, prompts ──────────────────│
     │◄── offer_mcp : McpTool « calc__calculate » dans le ToolManager,      │
     │    McpPromptCommand « /calc:explain » dans les commandes             │
     │                                                                      │
 ── l'utilisateur : « Combien font 1234*5678 ? » ──                         │
     │  answer : ce qui a changé depuis (relance, list_changed) est relu    │
     │  modèle ──► tool_call calc__calculate {"expression": "1234*5678"}    │
     │  risque ? (plan si irréversible)    permission ? (sauf lecture seule)│
     │  McpTool.handle ── connect() ───►│  (relancé d'abord s'il a planté)      │
     │                              │──── tools/call {…, _meta.progressToken}►│
     │                              │◄─── notifications/progress (0..n) ────│  « … 2/5 »
     │                              │◄─── {content, isError: false} ────────│
     │◄── « 1234*5678 = 7006652 » ──│                                       │
     │  modèle ──► « 1234 × 5678 = 7 006 652. »                             │
     │                                                                      │
 ── Ctrl+D ──                                                               │
     │  App.close() ───────────────►│  stdio : stdin fermé → SIGTERM →      │
     │                              │  SIGKILL au groupe ; HTTP : DELETE ──►│  arrêté
```

### Le client et ses transports

`McpClient` (`client.py`) est **synchrone pour Louis**, qui l'est aussi : `request()` envoie la requête puis attend sa réponse dans une file (`queue.Queue`), au plus `timeout` secondes. Ce qu'écrit le serveur arrive d'un autre thread : une réponse va dans la file de la requête qui l'attend, retrouvée par son `id` ; une requête du serveur reçoit une réponse tout de suite. Quand le serveur ne peut plus répondre (il s'est arrêté, la session HTTP a expiré), toutes les requêtes en attente reçoivent l'erreur.

Le client ne sait pas comment le serveur est joint. Il parle à un **transport** : `open(receive, closed)`, `send(message)`, `close()`, et `running`. Les deux transports :

**stdio** (`transport_stdio.py`) :

- **Sa propre session** (`start_new_session=True`). Un Ctrl+C dans le terminal arrête la réponse en cours, pas les serveurs.
- **Un environnement réduit.** Le serveur ne reçoit de Louis que `HOME`, `PATH`, `USER`, `LOGNAME`, `SHELL`, `TERM`, `LANG`, `LC_ALL`, `TZ` et `TMPDIR` (comme le SDK officiel), plus le `env` de sa déclaration. Un jeton GitHub dans l'environnement de Louis n'arrive donc jamais à un serveur qui n'en a pas besoin.
- **Deux threads** : le lecteur (une ligne qui n'est pas du JSON est ignorée) et le vidangeur, qui écrit la sortie d'erreur dans `louis.log`. Le tuyau ne se remplit jamais, et rien n'est écrit sur le terminal, où la fenêtre curses serait abîmée. Les 5 dernières lignes disent souvent pourquoi un serveur n'a pas démarré.
- **L'arrêt suit la spécification stdio.** L'entrée du serveur est fermée et il a 2 s pour sortir. Sinon il reçoit SIGTERM, puis SIGKILL. Les signaux vont à **tout son groupe** : `npx` lance `node`, qui survivrait sinon.

**HTTP** (`transport_http.py`), le Streamable HTTP de la spécification 2025-06-18 :

- **Chaque message part dans son thread** (POST), si bien que `request()` attend sa réponse comme en stdio. Les en-têtes : `Accept: application/json, text/event-stream`, puis `Mcp-Session-Id` (donné par le serveur à `initialize`) et `MCP-Protocol-Version` (la version convenue), et ceux de la déclaration (un jeton).
- **La réponse** est du JSON, ou un **flux d'événements** (SSE) : la progression et les requêtes du serveur y passent avant la réponse. `202` : rien à lire (une notification).
- **Le serveur parle de lui-même** sur un flux qu'il garde ouvert (GET), lancé après `notifications/initialized` : ses outils qui changent, ses journaux. Un serveur qui n'en a pas répond `405`, et rien d'autre n'est demandé.
- **Ce qui va mal** : une erreur HTTP est l'erreur de la requête (`HTTP 401 … vérifie le token de ses headers`). Une session que le serveur a oubliée (`404`) ou une adresse qui ne répond plus rendent le serveur « planté » : il est rouvert au prochain appel, comme un programme relancé.
- **L'arrêt** : `DELETE` avec la session, et le flux du serveur fermé.

Le transport HTTP a été essayé contre `@modelcontextprotocol/server-everything` en mode `streamableHttp` : session, réponses en flux, progression de `trigger-long-running-operation`.

### Pourquoi un client à nous, et pas le SDK officiel

Le SDK Python `mcp` est asynchrone (anyio) et apporte une quinzaine de dépendances (pydantic, httpx, starlette, uvicorn…). Il aurait fallu faire tourner une boucle asyncio dans un thread pour l'appeler depuis Louis, qui est synchrone. Le client et ses deux transports tiennent en un peu plus de 700 lignes de Python standard, commentaires compris, sans aucune bibliothèque, et contrôlent exactement les timeouts, les plantages, la relance et l'arrêt. Le client a été essayé contre des serveurs écrits avec les SDK officiels : `mcp-server-time` (Python), `@modelcontextprotocol/server-filesystem` et `@modelcontextprotocol/server-everything` (Node, en stdio et en HTTP) ; et dans l'autre sens, Louis serveur a été lu par le MCP Inspector officiel.

### Où sont déclarés les serveurs (`config.py`)

Trois sources, lues dans cet ordre ; un serveur remplace celui du même nom déclaré avant lui :

1. les réglages, `mcp.servers` (une liste ; c'est là que sont `calc` et `time`) ;
2. `~/.config/louis/mcp.json`, les serveurs de l'utilisateur ;
3. `.mcp.json`, dans le dossier du projet.

Les fichiers ont le **format de Claude Code, Cursor et Claude Desktop** (`{"mcpServers": {"<nom>": {…}}}`) : un fichier de l'un d'eux se copie tel quel, les clés que Louis ne connaît pas sont ignorées. Louis y ajoute les siennes : `risk`, `enabled`, `tools` et `exclude`.

- **`${VAR}` et `${VAR:-défaut}`** sont remplacés par la variable d'environnement de Louis, dans `command`, `args`, `env`, `url` et `headers`. Un jeton se nomme dans le fichier, il n'y est jamais écrit. Une variable absente, sans défaut, laisse ce serveur de côté, avec son nom dans `/mcp`.
- **Chaque déclaration est vérifiée** : un serveur mal déclaré, ou un fichier qui n'est pas du JSON valide, est un serveur « n'a pas démarré » dont `/mcp` dit pourquoi (`fichier JSON invalide (ligne 3)`, `réglage invalide : tools et exclude sont des listes…`). Le transport `sse` (l'ancien HTTP de MCP) est refusé avec ce qu'il faut faire à la place.
- **`tools` et `exclude`** filtrent les outils proposés au modèle, par leur nom sur le serveur, avec `*`. Un modèle de 9 milliards de paramètres choisit mal parmi les 14 outils du serveur de fichiers : on lui en donne 3. `/mcp` dit combien sont masqués.
- **`enabled: false`** : le serveur est déclaré mais pas lancé (« désactivé ») ; `/mcp restart` le lance.

#### Les serveurs du projet attendent ton accord

Un `.mcp.json` vient avec le projet : cloner un dépôt et y lancer Louis lancerait les commandes que son auteur y a écrites. Les serveurs d'un fichier du projet (un chemin relatif de `mcp.files`) sont donc **en attente** : ni lancés ni proposés au modèle, ils apparaissent dans `/mcp` avec leur commande. `/mcp trust <nom>` les approuve et les lance.

L'accord est gardé dans `~/.config/louis/mcp-trusted.json`, **hors de tout projet** (un projet ne peut pas s'approuver lui-même) : pour chaque dossier, l'empreinte SHA-256 de chaque déclaration telle qu'elle est écrite. Une commande ou un argument changé est un autre serveur, qui attend un nouvel accord. Le fichier est écrit en entier puis mis en place (`os.replace`) : un Louis qui s'arrête en l'écrivant le laisse tel qu'il était.

### La vie d'un serveur

| État | Ce qu'il veut dire | Ce qui en sort |
| --- | --- | --- |
| `running` (actif) | il répond | `/mcp stop` → `stopped` ; un plantage → `crashed` |
| `failed` (n'a pas démarré) | sa déclaration est invalide, ou il n'a pas démarré | `/mcp restart` (sauf déclaration invalide) |
| `crashed` (s'est arrêté) | il s'est arrêté de lui-même, ou sa session HTTP a expiré | relancé au prochain appel, `mcp.restarts` fois ; `/mcp restart` |
| `stopped` (arrêté) | Louis l'a arrêté | `/mcp restart` seulement : jamais relancé de lui-même |
| `disabled` (désactivé) | `enabled: false` | `/mcp restart` |
| `pending` (attend ton accord) | déclaré par le projet | `/mcp trust` |

- **La relance automatique** se fait au prochain appel d'un outil du serveur (`McpServer.connect`), `mcp.restarts` fois (1 par défaut). **L'appel qui a vu le serveur planter n'est jamais refait** : il a peut-être agi avant le plantage. Le modèle lit « il sera relancé au prochain appel », ou, sans relance restante, « fais sans cet outil ».
- **Un outil fait avant une relance marche encore après** : `McpTool` garde son `McpServer`, pas le client, et appelle le client du moment.
- **Les listes qui changent** : le thread qui lit le serveur note seulement que ses outils ou ses prompts ont changé (il ne touche jamais au `ToolManager`). Avant chaque message de l'utilisateur, `App.answer` relit ce qui a changé et propose les nouveaux outils ; l'utilisateur voit une ligne (`MCP : fake a changé ses outils (12 outils)`). Un serveur qui annonce un changement mais liste les mêmes outils (`server-everything` le fait en démarrant) n'est pas un changement.
- **Les commandes** `/mcp restart|stop|trust` et ces changements envoient `MCP_CHANGED` : une ligne dans le terminal, une notice sur la page, et la liste des commandes à jour pour la complétion (les prompts du serveur arrivent ou partent avec lui).

#### L'ordre des outils

Ollama garde en mémoire ce qu'il a déjà lu de la conversation : une requête qui commence comme la précédente n'est relue qu'à partir de ce qui a changé. La liste des outils est au début de chaque requête. Pendant la démo, `/mcp stop calc` puis `/mcp restart calc` remettaient `calc__calculate` à la fin de la liste : la requête suivante ne commençait plus pareil, et le modèle, qui tournait sur le processeur, a relu toute la conversation (plusieurs minutes). `App.offer_mcp` propose donc toujours les outils dans le même ordre : ceux de Louis, puis ceux des serveurs, serveur après serveur. Les mêmes outils font la même requête.

### Progression et journaux

- **La progression** : chaque `tools/call` porte un `progressToken` (l'`id` de la requête). Les `notifications/progress` du serveur vont dans la file de la requête qui attend, et dans le thread de Louis :
  - **l'utilisateur voit où en est l'appel** (`… everything__trigger-long-running-operation : 2/3`, une barre sur la page web), au plus toutes les 0,5 s sauf si le serveur dit quelque chose de nouveau ;
  - **le timeout repart** : un serveur qui dit travailler est attendu `mcp.timeout` secondes de plus à chaque étape, mais `mcp.max_timeout` (600 s) en tout au plus, comme le demande la spécification. Un serveur qui travaillerait sans fin n'est pas attendu sans fin.
- **Les journaux** : si le serveur en a (`logging`), Louis lui demande ceux de `mcp.log_level` et au-dessus (`info`), et ses `notifications/message` vont dans `louis.log` au niveau correspondant, jamais à l'écran.

### Les prompts

Un prompt MCP est un message que le serveur écrit pour l'utilisateur, avec des arguments. Chaque prompt d'un serveur actif devient une commande `/<serveur>:<prompt>` (`McpPromptCommand`), avec son usage (`/calc:explain <expression>`) et sa description, dans l'aide et la complétion.

- **Les arguments** : un seul, et c'est tout le texte tapé ; plusieurs, et ce sont des mots dans l'ordre, ou `nom=valeur`, entre guillemets pour les espaces. Un argument requis qui manque, un argument de trop ou un guillemet non fermé sont dits à l'utilisateur, sans rien envoyer.
- **Le texte** du serveur (`prompts/get`) devient le message de l'utilisateur, et un tour du modèle suit (`App.answer`). Ce que le serveur a écrit comme réponse de l'assistant est marqué `(réponse de l'assistant)` : le modèle le lit comme un exemple, jamais comme ses propres mots.
- **Il passe par le garde-fou** comme tout message : c'est du texte qu'un autre programme a écrit.

`calc` a un prompt, `explain` : `/calc:explain (3+4)*sqrt(16)` demande au modèle de calculer avec l'outil, puis d'expliquer chaque étape. En direct, le modèle a appelé `calc__calculate`, obtenu `28`, puis détaillé les parenthèses, la racine et la multiplication.

### Louis comme serveur MCP (`serve.py`)

`louis --mcp-server` lit des messages JSON-RPC sur son entrée et répond sur sa sortie, jusqu'à ce que le client la ferme. Il offre les outils de Louis **qui ne font que lire**, annotés `readOnlyHint` :

- `tree`, `cat_file` et `search` : les fichiers du projet où il a été lancé. Ces outils sont **gardés dans le projet** (`resolve_path`) : `../secret` est refusé.
- `search_knowledge` dès que quelque chose est indexé, avec la liste des sources dans sa description. La base est relue tant qu'elle est vide : un dossier indexé (`louis --index`) pendant qu'un client garde le serveur ouvert y apparaît.

Rien qui écrive, rien qui sorte de la machine, et personne à qui demander une permission : un outil qui en demanderait une est refusé. Une erreur d'un outil est une erreur pour le client (`isError`), jamais un arrêt du serveur. **Sa sortie est le protocole seul** : ce qu'une bibliothèque écrirait avec `print` part sur la sortie d'erreur, et le journal va dans `louis.log`.

```bash
claude mcp add louis -- /chemin/vers/sensai/venv/bin/python /chemin/vers/sensai/src/main.py --mcp-server
npx @modelcontextprotocol/inspector --cli venv/bin/python src/main.py --mcp-server --method tools/list
```

### Le serveur `calc` (`servers/calc.py`)

C'est l'exemple du sujet : le modèle utilise sa calculatrice au lieu de calculer de tête. `calc` est un serveur MCP complet, en Python standard, qui ne dépend pas de Louis. Il répond à `initialize`, `ping`, `tools/list`, `tools/call`, `prompts/list` et `prompts/get`. Son outil `calculate` évalue une expression **sans `eval`** :

- l'expression est découpée par `ast`, et chaque nœud est vérifié ;
- seuls l'arithmétique, les constantes (`pi`, `e`…) et les fonctions de `math` sont permis ;
- une puissance de plus de 100 000 chiffres, ou une factorielle au-delà de 25 000, est refusée, pour que le serveur ne bloque pas.

Une division par zéro ou une expression mal écrite renvoie `isError: true` : le modèle la lit comme une erreur. L'outil se déclare en lecture seule (`readOnlyHint`), et ne demande donc jamais de permission.

### L'outil (`tool_mcp.py`)

- **Son nom** est `<serveur>__<outil>`. Les caractères qu'un nom d'outil ne peut pas contenir pour Ollama deviennent `_`, et le nom est coupé à 64 caractères. Un serveur ne peut pas prendre le nom d'un outil de Louis : celui-là est laissé de côté, avec un avertissement.
- **Sa description** est celle du serveur, précédée de `[MCP <serveur>]`. **Ses paramètres** sont le `inputSchema` du serveur, sans `$schema`.
- **Son résultat** devient du texte : les parties texte sont gardées, une image est seulement nommée (`[image image/png]`), une ressource donne son texte ou son URI, et `structuredContent` sert quand il n'y a pas de texte. `isError` donne `Erreur : <texte>`.

### Risque, permissions et plan

Un outil MCP s'insère dans le système de risque de Louis (`tool/risk.py`) comme les autres :

| Ce que dit le serveur (annotations) | Risque | Ce qui se passe |
| --- | --- | --- |
| `readOnlyHint: true` | `safe` | rien n'est demandé |
| `destructiveHint: false` | `reversible` | l'outil demande ta permission avant d'agir |
| rien, ou autre chose | `irreversible` | la réponse est suspendue et le plan montré (`/plan`) ; sans plan, la permission est redemandée chaque fois |

Le dernier cas suit la règle de Louis : **un risque inconnu n'est jamais pris pour nul**. Louis ne sait pas ce que fait l'outil d'un autre programme. Si l'on fait confiance à un serveur, `"risk"` impose un niveau à tous ses outils. Un plan approuvé ne redemande rien, et le refuser n'appelle pas l'outil : le système de plan existant s'en charge, sans code en plus.

Avec le garde-fou actif, le résultat d'un outil MCP passe par les rails des résultats d'outils, comme celui de la base de connaissances : c'est du texte qu'un autre programme a écrit, qui peut contenir des instructions adressées au modèle (injection de prompt).

### Ce qui peut mal tourner

| Situation | Ce que voit le modèle | Ce que voit l'utilisateur |
| --- | --- | --- |
| Commande introuvable | pas les outils du serveur | « time : n'a pas démarré », `/mcp` dit « la commande uvx est introuvable » |
| Le serveur sort au démarrage | pas ses outils | sa raison et sa dernière ligne d'erreur dans `/mcp` |
| Pas de réponse en `mcp.start_timeout` | pas ses outils | « pas de réponse à initialize après 60 s » |
| Déclaration invalide, fichier `.mcp.json` illisible | pas ses outils | « réglage invalide : … » ou « fichier JSON invalide (ligne N) » dans `/mcp` |
| Variable `${VAR}` absente | pas ses outils | « la variable GITHUB_TOKEN n'est pas définie » |
| Serveur du projet pas encore approuvé | pas ses outils | « attend ton accord (/mcp trust …) » |
| Serveur HTTP qui refuse le jeton | pas ses outils | « HTTP 401 Unauthorized : … vérifie le token de ses headers » |
| L'outil renvoie `isError` | `Erreur : <son message>` | l'appel est marqué en échec |
| Appel plus long que `mcp.timeout` (sans progression) ou que `mcp.max_timeout` | `Erreur : … n'a pas répondu à X en 30 s` | idem |
| Le serveur plante pendant un appel | `Erreur : … s'est arrêté pendant X … Il sera relancé au prochain appel.` | `/mcp` : « s'est arrêté » |
| Appel suivant | le serveur est relancé, l'appel se fait | « MCP : fake relancé » au message suivant |
| Plus de relance possible | `Erreur : … ne répond plus` | `/mcp restart` |
| Session HTTP expirée, adresse qui ne répond plus | `Erreur : …`, puis rouvert au prochain appel | idem |
| Permission refusée | `Refusé : …` | — |
| Prompt sans son argument requis, ou en erreur sur le serveur | rien n'est envoyé | l'usage de la commande, ou l'erreur du serveur |

Aucune de ces situations ne lève d'exception jusqu'à Louis. Un serveur qui ne démarre pas ne retarde pas les autres, puisqu'ils démarrent en parallèle.

## Tests

93 tests, sur de vrais processus et un vrai serveur HTTP, en 16 s environ :

```bash
venv/bin/pytest tests/test_mcp*.py -v
```

| Fichier | Tests | Ce qu'ils vérifient |
| --- | --- | --- |
| `test_mcp.py` | 27 | outils découverts (y compris sur plusieurs pages), appel réussi, appels en échec (division par zéro, `isError`, outil inconnu, timeout, plantage), serveurs qui ne démarrent pas, déclarations invalides, risque et permissions, environnement réduit, `roots/list`, arrêt ; dans Louis avec un modèle scripté : l'appel, le plan, `/mcp`, `App.close()` |
| `test_mcp_lifecycle.py` | 10 | relance automatique (une fois, jamais l'appel qui a planté), serveur arrêté jamais relancé de lui-même, `list_changed` relu au message suivant, `/mcp stop|restart` et leurs erreurs, l'ordre des outils après une relance, une liste annoncée mais inchangée |
| `test_mcp_progress.py` | 7 | progression qui repousse le timeout, plafond `mcp.max_timeout`, étapes espacées, progression vue par l'utilisateur ; `logging/setLevel` et journaux dans `louis.log` à leur niveau |
| `test_mcp_config.py` | 13 | `.mcp.json` au format de Claude Code, `${VAR}` et `${VAR:-défaut}`, remplacement par nom, fichiers invalides, `tools`/`exclude`, `enabled: false`, serveurs du projet en attente, `/mcp trust`, accord gardé hors du projet et perdu quand la déclaration change |
| `test_mcp_http.py` | 14 | un faux serveur HTTP dans le test : JSON, flux avec progression, requête du serveur dans un flux, session et version dans les en-têtes, jeton de l'environnement (et jamais montré dans `/mcp`), 401, session oubliée puis rouverte, serveur injoignable, `DELETE` à la fermeture, flux du serveur (GET), lecture des SSE |
| `test_mcp_prompts.py` | 17 | prompts en commandes dès le démarrage, prompt envoyé au modèle (qui appelle `calc__calculate`), réponse de l'assistant marquée, erreurs (argument manquant, serveur en erreur, prompt vide, guillemet), commandes qui partent et reviennent avec le serveur, prompts ajoutés en cours de route, un chemin tapé en premier reste un message, lecture des arguments |
| `test_mcp_serve.py` | 5 | `--mcp-server` lancé comme un serveur par le client de Louis : ses outils de lecture, gardés dans le projet, sans `edit_file` ; `search_knowledge` une fois indexé ; erreurs d'outil pour le client ; protocole et versions ; rien d'autre que le protocole sur sa sortie |

### Essayer pour de vrai

```bash
pip install uv                          # pour lancer mcp-server-time avec uvx
python src/main.py
> /mcp
> Quelle heure est-il à Tokyo en ce moment ?     # → time__get_current_time
> Combien font 1234 * 5678 + 91 ?                # → calc__calculate
> /calc:explain (3+4)*sqrt(16)                   # le prompt de calc
> /mcp stop calc                                 # ses outils ne sont plus proposés
> /mcp restart calc
```

Pour voir la progression, les prompts d'un autre serveur et l'accord du projet, un `.mcp.json` dans le dossier où on lance Louis :

```json
{"mcpServers": {"everything": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-everything"],
                               "risk": "safe", "exclude": ["get-env", "gzip-*", "toggle-*"]}}}
```

```
> /mcp trust everything
> Utilise everything__trigger-long-running-operation avec duration 3 et steps 3.
  ● everything__trigger-long-running-operation duration=3 steps=3
  … everything__trigger-long-running-operation : 1/3
  … everything__trigger-long-running-operation : 2/3
  … everything__trigger-long-running-operation : 3/3
```

## Limites

- **Les outils et les prompts**, pas les **ressources** de MCP (`resources/list`, `resources/read`) : une ressource dans un résultat est seulement nommée.
- **Pas d'échantillonnage ni d'élicitation** : un serveur ne peut pas demander au modèle de Louis d'écrire, ni poser une question à l'utilisateur. Ces requêtes reçoivent « méthode inconnue ».
- **Pas de transport `sse`** (l'ancien HTTP de MCP, d'avant 2025) : la plupart des serveurs offrent aussi le Streamable HTTP.
- **Pas d'OAuth** pour les serveurs HTTP : un jeton se donne dans `headers`, depuis une variable d'environnement.
- **Changer les outils coûte une relecture** : arrêter un serveur, en approuver un, ou un serveur qui change ses outils, change le début des requêtes ; Ollama relit alors la conversation une fois. Sur un processeur, c'est long.
- Les annotations d'un serveur sont ce qu'il dit de lui-même. Un serveur malveillant peut se déclarer en lecture seule : ne déclare que des serveurs auxquels tu fais confiance, ou impose leur risque avec `"risk"`. L'accord du projet protège du `.mcp.json` d'un dépôt cloné, pas d'un serveur qu'on a choisi.
- **Louis serveur** n'offre que la lecture, et sans le garde-fou : c'est le client qui l'appelle qui juge ce qu'il en fait.
