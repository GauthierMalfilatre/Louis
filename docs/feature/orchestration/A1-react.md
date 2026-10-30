# A1 · Raisonnement pas à pas (ReAct)

Louis peut répondre **pas à pas**, en rendant son raisonnement visible et vérifiable : utile quand la façon d'arriver à la réponse compte autant que la réponse.

## Ce qu'il fait

- **Chaque étape est dite** : avant chaque action, le modèle écrit ce qu'il sait, ce qui lui manque et ce qu'il va faire, puis lit le résultat de ses outils avant l'étape suivante.
- **La réponse est vérifiée avant d'être donnée** : un fichier qu'elle cite sans qu'aucun outil l'ait lu la fait refuser tout de suite ; sinon le modèle reprend chacune de ses affirmations avec sa source (un résultat d'outil, un calcul refait) et conclut.
- **Réécrite si besoin** : une réponse refusée est réécrite avec ses problèmes (`reason.attempts` fois au plus) ; la dernière est donnée quoi qu'il arrive, avec ce qui reste à redire.
- **Tu ne vois que la réponse vérifiée.** Les brouillons refusés restent dans la session, comme trace, mais pas dans `/export`, `/share` ni `/resume`.
- Chaque étape et chaque vérification vont dans les traces (`step`, `check`) ; le tableau de bord montre la part des réponses justes du premier coup, réécrites, ou données avec des problèmes.
- C'est **plus lent** : chaque vérification est une requête de plus au modèle. Indépendant de `/think`, qui fait réfléchir le modèle avant chaque réponse dans les deux modes.

## Commandes

| Commande | Comment ça marche | À quoi ça sert |
| -------- | ----------------- | -------------- |
| `/react` | bascule le pas à pas pour les messages suivants (bouton « Pas à pas » sur la page web) | voir et faire vérifier le raisonnement |
| `louis --react` | démarre en pas à pas (comme `reason.enabled: True`) | l'avoir dès le premier message |
| `/think` | le modèle réfléchit avant chaque réponse, dans les deux modes | ajouter de la réflexion, sans vérification |
| `reason.verify`, `reason.attempts` | réglages : couper la vérification, nombre de réécritures | plus rapide, ou plus exigeant |

## Exemples

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

```bash
louis --react      # démarre en pas à pas (réglage reason.enabled) ; bouton « Pas à pas » sur la page web
```

`reason.verify: False` coupe la vérification. Tests : `tests/test_reason.py`.
