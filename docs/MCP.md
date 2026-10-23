# Client MCP

Louis sait appeler des outils pendant qu'il répond : le modèle s'interrompt, émet un appel structuré (le nom d'un outil et ses arguments), Louis l'exécute, lui rend le résultat, et le modèle continue sa réponse avec. Jusqu'ici, ces outils étaient tous écrits dans Louis (`cat_file`, `git`, `web_search`…).

Cette fonctionnalité fait de Louis un **client MCP** ([Model Context Protocol](https://modelcontextprotocol.io)) : n'importe quel programme qui parle MCP lui apporte ses outils, sans une ligne de code dans Louis. On le déclare dans les réglages, Louis le lance, lui demande ses outils et les donne au modèle avec les siens.

## Ce que fait la fonctionnalité

| Exigence | Où |
| --- | --- |
| Le modèle appelle un outil, Louis l'exécute, rend le résultat, le modèle continue | inchangé : `App.__call` (`src/app/app.py`) |
| Serveurs déclarés dans les réglages (`mcp.servers` : `name`, `command`, `args`, `env`), en stdio | `src/config/settings.py` |
| Au démarrage, chaque serveur est lancé, ses outils listés et enregistrés sous `<serveur>__<outil>` | `McpManager.start`, `App.__init__` |
| Un appel du modèle passe par `call_tool`, son résultat est rendu au modèle | `McpTool.handle`, `McpClient.call_tool` |
| Erreur MCP, timeout ou serveur planté → résultat `Erreur : …`, jamais un plantage | `McpTool.handle`, `McpClient` |
| Un serveur qui ne démarre pas est noté dans le log et laissé de côté | `McpManager.__start` |
| Les outils MCP passent par les permissions et le plan | `McpTool.risk`, `McpTool.handle` |
| Les serveurs sont arrêtés proprement quand Louis se ferme | `App.close`, `McpClient.close`, `atexit` |
| `/mcp` liste les serveurs, leur état et leurs outils | `src/command/impl/command_mcp.py`, les interfaces |
| Démo avec un serveur existant et un serveur à nous | `time` (mcp-server-time) et `calc` (le nôtre) |
| `tests/test_mcp.py` : outils découverts, appel réussi, appel en échec, serveur qui ne démarre pas | `tests/test_mcp.py`, `tests/mcp_fake_server.py` |
| README : comment ajouter un serveur MCP | `README.md`, section « Serveurs MCP » |

## Les changements, fichier par fichier

Tout le code MCP est dans `src/tool/mcp/` : un outil MCP est un outil de Louis comme les autres.

| Fichier | Rôle |
| --- | --- |
| `src/tool/mcp/client.py` (nouveau) | `McpClient` : lance un serveur et lui parle en JSON-RPC 2.0 sur son entrée et sa sortie standard. Aucune dépendance. |
| `src/tool/mcp/tool_mcp.py` (nouveau) | `McpTool` : un outil d'un serveur, vu par le modèle comme un outil de Louis. Son nom, son schéma, son risque, son appel, et la conversion du résultat en texte. |
| `src/tool/mcp/manager.py` (nouveau) | `McpManager` et `McpServer` : les serveurs des réglages, démarrés en parallèle, leur état, leurs outils, leur arrêt. |
| `src/tool/mcp/servers/calc.py` (nouveau) | `calc`, **notre serveur MCP** : une calculatrice exacte. C'est un programme à part, que Louis lance comme n'importe quel serveur. |
| `src/config/settings.py` | `mcp.servers` (`calc` et `time` par défaut), `mcp.timeout`, `mcp.start_timeout`. |
| `src/events/event_list.py` | `MCP_STARTED` (au démarrage) et `MCP_SERVERS` (pour `/mcp`). |
| `src/app/app.py` | Démarre les serveurs, enregistre leurs outils, `App.mcp`, `App.close()`. Les résultats MCP passent par le garde-fou. `/mcp` est enregistrée. |
| `src/main.py` | `app.close()` à la fin de `run()`, même en cas de plantage. `--ask` (JSON, sans outils) ne lance aucun serveur. |
| `src/command/impl/command_mcp.py` (nouveau) | La commande `/mcp`. |
| `src/interface/cli.py` | Une ligne au démarrage, et la liste de `/mcp`, dans le terminal et dans la fenêtre curses (qui hérite du CLI). |
| `src/interface/web.py` | Les mêmes informations dans l'interface web : une notice et une carte. |
| `tests/mcp_fake_server.py` (nouveau) | Un faux serveur MCP qui échoue sur commande (trop lent, plante, ne démarre pas…). |
| `tests/test_mcp.py` (nouveau) | 27 tests, sur de vrais processus. |
| `tests/conftest.py` | Les tests qui créent une `App` ne lancent aucun serveur, sauf ceux qu'ils déclarent. |
| `README.md` | La section « Serveurs MCP ». |

### Les commits

La branche `feat/mcp-client` part de `feat/human-in-the-loop`, car le plan (`Tool.risk`, `tool/risk.py`) n'existe que là. Un commit par fichier ou par fonctionnalité, dans cet ordre, et les tests passent après chacun :

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

## Comment ça marche

### Le protocole

Un serveur MCP en stdio est un programme que Louis lance. Ils s'échangent des messages **JSON-RPC 2.0**, un par ligne : Louis écrit sur l'entrée standard du serveur, le serveur répond sur sa sortie standard. Sa sortie d'erreur est faite pour les logs.

- Une **requête** a un `id`, une `method` et des `params`. Sa **réponse** reprend le même `id`, avec un `result` ou une `error`.
- Une **notification** n'a pas d'`id` : on n'y répond pas.

Louis utilise quatre méthodes : `initialize` (accord sur la version du protocole), `notifications/initialized`, `tools/list` (les outils, page par page) et `tools/call` (l'appel d'un outil). Le serveur peut aussi faire des requêtes à Louis : `ping` reçoit `{}`, `roots/list` reçoit le dossier du projet, et les autres une erreur `-32601` (méthode inconnue).

### Du démarrage à la réponse

```
 Louis (App)              McpManager / McpClient                 serveur MCP (processus)
     │                              │                                       │
     │  McpManager(settings)        │                                       │
     │  .start() ──────────────────►│  un thread par serveur, en parallèle  │
     │                              │  Popen([command, *args]) ────────────►│  lancé dans sa propre session
     │                              │──── initialize ──────────────────────►│
     │                              │◄─── protocolVersion, capabilities ────│
     │                              │──── notifications/initialized ───────►│
     │                              │──── tools/list (puis nextCursor…) ───►│
     │                              │◄─── [{name, description,              │
     │                              │       inputSchema, annotations}] ─────│
     │◄── McpTool « calc__calculate »                                       │
     │    enregistré dans le ToolManager, avec les outils de Louis          │
     │                                                                      │
 ── l'utilisateur : « Combien font 1234*5678 ? » ──                         │
     │                                                                      │
     │  modèle ──► tool_call calc__calculate {"expression": "1234*5678"}    │
     │  risque ? (plan si irréversible)                                     │
     │  permission ? (sauf lecture seule)                                   │
     │  McpTool.handle ────────────►│──── tools/call {name, arguments} ────►│
     │                              │◄─── {content: [{type: text, …}],      │
     │                              │      isError: false} ─────────────────│
     │◄── « 1234*5678 = 7006652 » ──│                                       │
     │  ajouté à la session (role: tool)                                    │
     │  modèle ──► « 1234 × 5678 = 7 006 652. »                             │
     │                                                                      │
 ── Ctrl+D ──                                                               │
     │  App.close() ───────────────►│  stdin fermé → attente → SIGTERM      │
     │                              │  → SIGKILL, à tout son groupe ───────►│  arrêté
```

### Le client (`client.py`)

`McpClient` est **synchrone pour Louis**, qui l'est aussi : `request()` envoie la requête puis attend sa réponse, au plus `timeout` secondes. Deux threads tournent derrière lui :

- **Le lecteur** lit la sortie du serveur ligne par ligne. Une réponse est rangée dans la file (`queue.Queue`) de la requête qui l'attend, retrouvée par son `id`. Une requête du serveur reçoit une réponse tout de suite. Une ligne qui n'est pas du JSON (un serveur qui écrit une bannière) est ignorée. Quand la sortie se ferme (le serveur s'arrête), toutes les requêtes en attente reçoivent l'erreur « le serveur s'est arrêté (code N) ».
- **Le vidangeur** lit la sortie d'erreur et l'écrit dans `louis.log`. Le tuyau ne se remplit jamais (un serveur bavard resterait bloqué), et rien n'est écrit sur le terminal, où la fenêtre curses serait abîmée. Les 5 dernières lignes sont gardées : elles disent souvent pourquoi un serveur n'a pas démarré.

Quelques choix :

- **Sa propre session** (`start_new_session=True`). Un Ctrl+C dans le terminal arrête la réponse en cours, pas les serveurs.
- **Un environnement réduit.** Le serveur ne reçoit de Louis que `HOME`, `PATH`, `USER`, `LOGNAME`, `SHELL`, `TERM`, `LANG`, `LC_ALL`, `TZ` et `TMPDIR` (comme le SDK officiel), plus le `env` de ses réglages. Un jeton GitHub dans l'environnement de Louis n'arrive donc jamais à un serveur qui n'en a pas besoin.
- **Timeout ou Ctrl+C.** Quand un appel dépasse `mcp.timeout` ou que l'utilisateur l'interrompt, Louis envoie `notifications/cancelled` : le serveur peut arrêter son travail. Une réponse arrivée trop tard est ignorée, et ne se mélange pas avec l'appel suivant.
- **L'arrêt suit la spécification stdio.** L'entrée du serveur est fermée et il a 2 s pour sortir. Sinon il reçoit SIGTERM, puis SIGKILL. Les signaux vont à **tout son groupe** : `npx` lance `node`, qui survivrait sinon. Un second `close()` ne fait rien.

### Pourquoi un client à nous, et pas le SDK officiel

Le SDK Python `mcp` est asynchrone (anyio) et apporte une quinzaine de dépendances (pydantic, httpx, starlette, uvicorn…). Il aurait fallu faire tourner une boucle asyncio dans un thread pour l'appeler depuis Louis, qui est synchrone. La partie de MCP dont Louis a besoin (stdio, `initialize`, `tools/list`, `tools/call`) tient en moins de 300 lignes de Python standard, commentaires compris. Ce code ne dépend d'aucune bibliothèque et contrôle exactement les timeouts, les plantages et l'arrêt, ce que les exigences demandent. Le client a été testé contre deux serveurs existants écrits avec les SDK officiels : `mcp-server-time` (Python) et `@modelcontextprotocol/server-filesystem` (Node).

### Le serveur `calc` (`servers/calc.py`)

C'est l'exemple du sujet : le modèle utilise sa calculatrice au lieu de calculer de tête. `calc` est un serveur MCP complet, en Python standard. Il lit les messages sur son entrée et répond à `initialize`, `tools/list`, `tools/call` et `ping`. Son outil `calculate` évalue une expression **sans `eval`** :

- l'expression est découpée par `ast`, et chaque nœud est vérifié ;
- seuls l'arithmétique, les constantes (`pi`, `e`…) et les fonctions de `math` sont permis ;
- une puissance de plus de 100 000 chiffres, ou une factorielle au-delà de 25 000, est refusée, pour que le serveur ne bloque pas.

Une division par zéro ou une expression mal écrite renvoie `isError: true` : le modèle la lit comme une erreur. L'outil se déclare en lecture seule (`readOnlyHint`), et ne demande donc jamais de permission.

### L'outil (`tool_mcp.py`)

- **Son nom** est `<serveur>__<outil>`. Les caractères qu'un nom d'outil ne peut pas contenir pour Ollama deviennent `_`, et le nom est coupé à 64 caractères. Deux serveurs peuvent avoir un outil du même nom, et un serveur ne peut pas prendre le nom d'un outil de Louis : celui-là est laissé de côté, avec un avertissement.
- **Sa description** est celle du serveur, précédée de `[MCP <serveur>]`. **Ses paramètres** sont le `inputSchema` du serveur, sans `$schema`.
- **Son résultat** devient du texte : les parties texte sont gardées, une image est seulement nommée (`[image image/png]`), une ressource donne son texte ou son URI, et `structuredContent` sert quand il n'y a pas de texte. `isError` donne `Erreur : <texte>`.

### Risque, permissions et plan

Un outil MCP s'insère dans le système de risque de Louis (`tool/risk.py`) comme les autres :

| Ce que dit le serveur (annotations) | Risque | Ce qui se passe |
| --- | --- | --- |
| `readOnlyHint: true` | `safe` | rien n'est demandé |
| `destructiveHint: false` | `reversible` | l'outil demande ta permission avant d'agir |
| rien, ou autre chose | `irreversible` | la réponse est suspendue et le plan montré (`/plan`) ; sans plan, la permission est redemandée chaque fois |

Le dernier cas suit la règle de Louis : **un risque inconnu n'est jamais pris pour nul**. Louis ne sait pas ce que fait l'outil d'un autre programme. Si l'on fait confiance à un serveur, le réglage `"risk"` impose un niveau à tous ses outils. Un plan approuvé ne redemande rien, et le refuser n'appelle pas l'outil : le système de plan existant s'en charge, sans code en plus.

Avec le garde-fou actif, le résultat d'un outil MCP passe par les rails des résultats d'outils, comme celui de la base de connaissances. C'est du texte écrit par un programme que personne ici n'a écrit : il peut contenir des instructions adressées au modèle (injection de prompt).

### Ce qui peut mal tourner

| Situation | Ce que voit le modèle | Ce que voit l'utilisateur |
| --- | --- | --- |
| Commande introuvable | pas les outils du serveur | « time : n'a pas démarré », `/mcp` dit « la commande uvx est introuvable » |
| Le serveur sort au démarrage | pas ses outils | sa raison et sa dernière ligne d'erreur dans `/mcp` |
| Pas de réponse en `mcp.start_timeout` | pas ses outils | « pas de réponse à initialize après 60 s » |
| Réglage invalide (pas de nom, `args` qui n'est pas une liste…) | pas ses outils | « réglage invalide : … » dans `/mcp` |
| L'outil renvoie `isError` | `Erreur : <son message>` | l'appel est marqué en échec |
| Appel plus long que `mcp.timeout` | `Erreur : … n'a pas répondu à X en 30 s` | idem |
| Le serveur plante pendant un appel | `Erreur : … le serveur s'est arrêté (code N)` | `/mcp` : « s'est arrêté » |
| Appel à un serveur déjà planté | `Erreur : … ne répond plus` | idem |
| Permission refusée | `Refusé : …` | — |

Aucune de ces situations ne lève d'exception jusqu'à Louis. Un serveur qui ne démarre pas ne retarde pas les autres, puisqu'ils démarrent en parallèle.

## Tests

`tests/test_mcp.py` lance de vrais processus : `calc`, et `tests/mcp_fake_server.py`, un faux serveur qui échoue sur commande. Ils durent environ 4 s.

- **Outils découverts** : leurs noms, leur description, leur schéma, sur une ou plusieurs pages de `tools/list`, même après une ligne qui n'est pas du JSON.
- **Appel réussi** : `calculate("2*(3+4)")` → `2*(3+4) = 14`.
- **Appel en échec** : division par zéro, `isError` du serveur, outil inconnu, timeout (la réponse tardive est ignorée), serveur qui plante (puis `crashed`, et `Erreur` aux appels suivants).
- **Serveur qui ne démarre pas** : commande introuvable, sortie au démarrage, pas de réponse, et chaque réglage invalide. Les autres serveurs marchent toujours.
- **Risque et permissions** : la lecture seule ne demande rien, un refus donne `Refusé`, le réglage `risk` l'emporte.
- **Sécurité** : le serveur ne reçoit pas une variable secrète de Louis, mais reçoit son `env`.
- **Arrêt** : après `close()`, plus aucun processus.
- **Dans Louis**, avec un modèle scripté :
  - le modèle appelle `calc__calculate`, le résultat est dans la session et le modèle le lit avant de répondre ;
  - un outil irréversible passe par le plan ;
  - `/mcp` liste les serveurs ;
  - `App.close()` les arrête.

```bash
venv/bin/pytest tests/test_mcp.py -v
```

### Essayer pour de vrai

```bash
pip install uv                          # pour lancer mcp-server-time avec uvx
python src/main.py
> /mcp
> Quelle heure est-il à Tokyo en ce moment ?     # → time__get_current_time
> Combien font 1234 * 5678 + 91 ?                # → calc__calculate
```

## Limites

- **stdio seulement** : pas de serveur distant (HTTP). C'est ce que demande le sujet, et le client est écrit pour qu'un autre transport remplace seulement le lancement et la lecture.
- **Les outils seulement** : pas les ressources ni les prompts de MCP, ni l'échantillonnage (le serveur qui demande au modèle de Louis d'écrire).
- **Les outils sont listés une fois, au démarrage.** Un serveur qui en change (`notifications/tools/list_changed`) est noté dans le log, mais il faut relancer Louis.
- **Un serveur planté n'est pas relancé** : ses appels donnent `Erreur`, et il faut relancer Louis.
- Les annotations d'un serveur sont ce qu'il dit de lui-même. Un serveur malveillant peut se déclarer en lecture seule : ne déclare que des serveurs auxquels tu fais confiance, ou impose leur risque avec `"risk"`.
