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

> Louis n'a pas encore de client MCP : les outils sont ceux de Louis, appelés par le tool calling d'Ollama.

Tests : `tests/test_tool_calls.py`.
