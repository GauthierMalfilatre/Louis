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

## Mesure réelle : avec et sans

`qwen3.5:9b` sur le processeur, `chat.context` à 12 288, nouvelle session à chaque texte. On a 4 signatures à transformer en contact. D'un côté `/json contact`, de l'autre un message qui demande « en JSON, avec exactement les champs nom, entreprise, poste, email, telephone, sans rien d'autre que le JSON ». On regarde si la sortie est utilisable telle quelle par un programme.

| | Sans (`JSON` demandé dans le texte) | Avec `/json contact` |
| - | - | - |
| JSON brut, lisible directement | 1 / 4 : les 3 autres sont dans un bloc ```` ```json ```` | 4 / 4 |
| Conforme au schéma, une fois le bloc enlevé | 4 / 4 | 4 / 4, au premier essai |
| Erreurs de contenu | « nom » : « Malfilatre », sans le prénom | « poste » vide pour « développeur chez Sensai », « entreprise » : la chaîne `"null"` |
| Tokens de prompt / temps par texte | ~3 870 / 282 à 297 s | ~1 515 / 112 à 124 s |

Ce qui change surtout, c'est la forme. Avec `/json`, on obtient à chaque fois du JSON brut, validé contre le schéma, que `louis --schema … --ask` peut passer directement à `jq`. Sans, le modèle l'enveloppe 3 fois sur 4 dans du Markdown, malgré la consigne. `/json` est aussi 2,5 fois plus rapide : il n'envoie ni les outils ni leurs ~2 300 tokens de schémas. Le schéma ne garantit pas le contenu : dans les deux cas, le modèle se trompe parfois sur une valeur. Ici, `"null"` en chaîne passe le schéma, parce que `entreprise` accepte n'importe quel texte.

Tests : `tests/test_structured.py`.
