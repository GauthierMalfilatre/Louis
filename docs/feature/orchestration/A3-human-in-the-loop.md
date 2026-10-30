# A3 · Plan avant d'agir (human in the loop)

Avant une action **qu'on ne peut pas défaire**, Louis s'arrête, montre son plan, et n'agit qu'après ton accord. Une réponse du modèle qui contient une telle action est suspendue **avant son premier appel** : tu vois ce que Louis veut faire, puis chacune de ses actions dans l'ordre, avec son risque, ce qu'elle fera, comment l'annuler, et ce qu'elle changera (le diff, les commits poussés…).

## Ce qu'il fait

- **Oui** : toutes les actions du plan se font, sans autre question. **Non** : aucune. **Répondre** : aucune, et ce que tu écris (« fais d'abord une branche ») est donné au modèle, qui propose autre chose.
- **Irréversible** : `git push`, supprimer une branche, ouvrir, commenter ou fusionner une pull request, remplacer ou modifier un fichier dont git n'a pas le contenu actuel. Un fichier commité tel quel, un commit, une branche ou un nouveau fichier sont réversibles.
- Une réponse sans action irréversible ne montre pas de plan : chaque outil demande ton accord comme avant. Un « toujours » donné à un outil ne laisse jamais passer une de ses actions irréversibles.
- **Personne pour répondre** (un script, `louis --ask`) : le plan est refusé, rien d'irréversible ne se fait.
- Chaque plan va dans les traces (`plan`) ; le tableau de bord montre la part des plans approuvés, refusés ou sans réponse, et le temps pris pour décider.

## Commandes

| Commande | Comment ça marche | À quoi ça sert |
| -------- | ----------------- | -------------- |
| `/plan` | dit si les plans sont actifs et à quel niveau | savoir ce qui sera demandé |
| `/plan off` / `/plan on` | coupe ou remet les plans (chaque outil demande quand même son accord) | travailler sans interruption, ou en sécurité |
| `/plan reversible` | un plan pour toute modification | tout relire avant que Louis agisse |
| `/plan irreversible` | (défaut) un plan seulement pour ce qui ne s'annule pas | n'être dérangé que pour l'important |
| `y` / `n` / `r` | approuve tout le plan / refuse tout / refuse et écris au modèle ce qu'il doit faire à la place | décider du plan |

## Exemples

```
Mon plan : je commite le README, puis je pousse la branche.
  1. Git action=commit message=docs: describe the project · réversible
     un commit sur docs/readme · annulable : git reset --soft HEAD~1 (les changements restent)
  2. Git action=push · IRRÉVERSIBLE
     les commits de docs/readme seront sur origin, visibles par toute l'équipe
a1b2c3d docs: describe the project
Approuver ce plan ? [y] oui  [n] non  [r] répondre
```

```
> /plan                 # ce qui est réglé
> /plan off | /plan on  # coupe et remet les plans
> /plan reversible      # un plan pour toute modification
> /plan irreversible    # (défaut) seulement pour ce qui ne s'annule pas
```

Réglages : `hitl.enabled`, `hitl.level`. Tests : `tests/test_plan.py`, `tests/test_risk.py`, `tests/test_permission.py`.
