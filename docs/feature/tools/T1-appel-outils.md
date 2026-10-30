# T1 · Appel d'outils (MCP)

Au milieu de sa réponse, le modèle peut appeler un outil au lieu de répondre : il donne son nom et ses arguments (le format `tools` d'Ollama), Louis l'exécute, lui renvoie le résultat, et le modèle continue avec. Il enchaîne autant d'appels qu'il faut, `chat.tools.maxdepth` tours au plus.

## Ce qu'il fait

- **Outils proposés** : la liste est dans [Commandes](#commandes) ; ceux qui ne servent pas (pas de Docker, base vide) ne sont pas proposés.
- **Un outil = une classe** : un `Tool` (nom, description, schéma JSON des paramètres, `handle()`) enregistré dans le `ToolManager`. Son schéma est envoyé au modèle tel quel.
- **Erreurs rendues au modèle** : un outil inconnu, des arguments faux ou un outil qui plante donnent un résultat `Erreur : …` que le modèle lit pour se corriger. Louis ne s'arrête jamais.
- **Garde-fous de la boucle** : le même appel répété en boucle est refusé, et un modèle qui annonce une action sans appeler d'outil est relancé une fois.
- Chaque appel s'affiche pendant qu'il tourne, puis se résume en une ligne (« J'ai lu calc.py. »).

## Commandes

Ces « commandes » sont appelées par le modèle, pas tapées par toi : il choisit l'outil et ses arguments, Louis l'exécute.

| Outil | Comment ça marche | À quoi ça sert |
| ----- | ----------------- | -------------- |
| `tree(path?, depth?)` | arborescence du dossier, dossiers d'abord | découvrir la structure du projet |
| `cat_file(path, start_line?, end_line?)` | lit un fichier, lignes numérotées | lire le code avant d'en parler |
| `search(pattern, path?, glob?)` | regex dans les fichiers, `chemin:ligne: contenu` | trouver où un nom est défini ou utilisé |
| `write_file` / `edit_file` / `mkdir` | écrivent dans le projet, après ton accord | créer et modifier du code ([T4](T4-acces-fichiers.md)) |
| `web_search(query)` | recherche DuckDuckGo | l'actualité, ce que le modèle ignore ([T3](T3-recherche-web.md)) |
| `run_code(language, code)` | exécute dans Docker | tester avant de répondre ([T2](T2-sandbox.md)) |
| `search_knowledge(query, …)` | cherche dans la base indexée | la doc et le code indexés ([R1](../rag/R1-rag-basique.md)) |
| `git(action, …)` | status, diff, log, branches, branch, delete_branch, pull, commit, push | suivre et publier son travail |
| `github_pr(action, …)` | list, view, create, comment, merge, par `gh` | gérer les pull requests |

## Exemple

```
> Combien de fichiers Python dans src/ ?
  ● Arborescence src (profondeur 3)
    ⎿ 112 entrées
  ● Recherche « \.py$ » dans src
    ⎿ 98 résultats
Il y a 98 fichiers Python dans src/.
```

Ajouter un outil :

```python
class AddTool(Tool):
    def __init__(self):
        super().__init__("add", "Additionne a et b.", {"type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}, "required": ["a", "b"]})

    def handle(self, app, **kwargs) -> str:
        return str(kwargs["a"] + kwargs["b"])

app._App__toolManager.register(AddTool())
```

> Louis est aussi un **client MCP** : les outils des serveurs MCP déclarés (`calc`, `time`, ceux d'un `.mcp.json`) sont proposés au modèle à côté de ceux-ci, sous le nom `<serveur>__<outil>`, et appelés de la même façon. Voir [T1 · Serveurs MCP](T1-serveurs-mcp.md).

## Mesure réelle : avec et sans

`qwen3.5:9b` sur le processeur, `chat.context` à 12 288, nouvelle session à chaque fois. La question : « Quels sont tous les champs de la dataclass Reply de ce projet (src/model/reply.py) ? ». On regarde la justesse.

| | Sans outils | Avec outils |
| - | - | - |
| Réponse | un bloc bash : `cat_file src/model/reply.py` | les 11 champs, dans l'ordre |
| Champs justes | 0 / 11 | **11 / 11** |
| Outils appelés | aucun | `cat_file` |
| Appels au modèle / tokens de prompt | 1 / 1 342 | 2 / 8 196 |
| Temps | 97 s | 317 s |

Sans outils, le modèle ne peut pas lire le fichier. Il écrit en texte la commande qu'il aurait voulu lancer, sans aucune réponse. Avec les outils, il lit le fichier et donne tous les champs. Ça coûte un appel de plus et 3 fois plus de temps : les schémas des outils pèsent ~2 500 tokens dans le prompt, et le fichier lu s'y ajoute.

Tests : `tests/test_tool_calls.py`.
