# T5 · Réponses structurées (JSON)

Louis peut répondre en JSON qui respecte un **schéma JSON** (les champs, leurs types, ceux qui sont obligatoires) au lieu de texte. Ollama empêche le modèle d'écrire autre chose, puis Louis vérifie la réponse et la redemande avec l'erreur si elle ne correspond pas (`structured.attempts` fois au plus, 3 par défaut). Une réponse qui ne correspond toujours pas n'est jamais renvoyée : c'est une erreur.

## Ce qu'il fait

- **Schémas** : cherchés par leur nom dans `schemas/` du projet (`structured.dir`), puis dans ceux de Louis (`src/structured/schemas/` : `todo`, `resume`, `contact`). Un schéma du projet cache celui de Louis du même nom. On peut aussi donner un fichier (`./mon_schema.json`).
- **Vérifié** : la réponse est validée par `jsonschema`, formats compris (`email`, `date`…). Un schéma invalide ou introuvable est signalé avec la raison.
- **Sans outils** : dans ce mode, le modèle n'a pas d'outils ; ce qu'il doit lire est dans la question.
- **Garde-fou** : une réponse masquée par [EV2](../evaluation/EV2-garde-fous.md) qui ne respecte plus le schéma est refusée.
- La réponse est gardée dans la session en bloc de code JSON. Le tableau de bord montre la part des réponses valides, et valides du premier coup.

## Commandes

| Commande | Comment ça marche | À quoi ça sert |
| -------- | ----------------- | -------------- |
| `/schemas` | liste les schémas du projet (`schemas/`) puis ceux de Louis, avec leur description ; un schéma cassé est signalé | savoir quels schémas sont disponibles |
| `/json <schéma> <question>` | répond en JSON qui respecte le schéma (nom ou fichier), le redemande s'il ne correspond pas | extraire des données d'un texte (contact, tâches, CV) |
| `/json <schéma>` | sans question : dit ce qui ne va pas dans le schéma | vérifier un schéma qu'on a écrit |
| `louis --schema <schéma> --ask "<question>"` | une question, le JSON seul sur stdout, le texte d'un pipe ajouté ; code de retour 0, 1 ou 2 | brancher Louis dans un script |

## Dans la conversation

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

## Depuis un script

La sortie est **seulement** le JSON, le texte envoyé par un pipe est ajouté à la question, les erreurs vont sur stderr.

```bash
cat compte-rendu.txt | louis --schema todo --ask "Extrais les tâches" > taches.json
louis --schema ./mon_schema.json --ask "..." | jq '.champ'
```

Code de retour : `0` réponse valide, `1` réponse invalide ou modèle injoignable, `2` schéma introuvable ou invalide.

Tests : `tests/test_structured.py`.
