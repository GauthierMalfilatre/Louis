# X3 · Export et publication

Une session s'exporte en JSON, Markdown, HTML ou PDF, avec les fichiers que Louis y a écrits. Elle se publie aussi par un lien public, sans compte, que l'on peut fermer.

## Ce qu'il fait

- **`/export [json|md|html|pdf] [id]`** : la session en cours, ou la session `<id>`, dans `exports/` (`export.dir`). La conversation, chaque appel d'outil avec son résultat, puis les **fichiers produits** en entier (refaits à partir des `write_file` et `edit_file` de la session).
- **`--artifact [fichiers]`** : seulement des fichiers écrits par Louis, par chemin, dossier (`src/`) ou motif (`*.py`) ; tous sans argument.
- **Formats** : JSON (relisible par un programme), Markdown, une page HTML autonome (sans script, thème clair et sombre), PDF à partir du HTML (WeasyPrint : `pip install -r requirements-export.txt`).
- **`/share [id] [--artifact …]`** : publie le document tel qu'il est maintenant, après t'avoir montré ce que le lien contiendra. Les données sensibles (clés, mots de passe, emails, cartes…) sont masquées, garde-fou actif ou non. L'accord est demandé à chaque fois.
- **`/shares`** liste tes liens ouverts, **`/unshare <lien>`** en ferme un (le lien, ou au moins 6 caractères du jeton).
- Le jeton (22 caractères aléatoires) est la seule clé du lien. Les pages sont servies par `louis --web` (`/s/<jeton>`), à l'adresse de `share.base_url` ou `LOUIS_SHARE_URL` si elle est donnée.
- Les brouillons refusés du pas à pas n'apparaissent jamais. Le partage demande un `--user`.

## Commandes

| Commande | Comment ça marche | À quoi ça sert |
| -------- | ----------------- | -------------- |
| `/export [json\|md\|html\|pdf] [id]` | écrit la session en cours (ou `<id>`) dans `exports/`, JSON par défaut | archiver, relire, transmettre |
| `/export … --artifact [fichiers]` | seulement les fichiers écrits par Louis (chemins, dossiers, motifs ; tous sans argument) | récupérer le code produit |
| `/share [id] [--artifact …]` | montre ce que le lien contiendra, masque les données sensibles, demande confirmation, crée le lien | partager une session sans compte |
| `/shares` | liste tes liens encore ouverts, du plus récent au plus ancien | retrouver un lien |
| `/unshare <lien>` | ferme le lien (le lien entier ou 6 caractères du jeton au moins) | retirer un partage |
| `pip install -r requirements-export.txt` | installe WeasyPrint | l'export PDF |

## Exemples

```
> /export md
✓ Session #15 exportée en Markdown (6 messages, 1 fichier) : ~/projet/exports/session-15.md
> /export pdf 12
> /export --artifact "src/*.py"
> /share
Publier la session #15 par un lien public ? :
  Titre   : Écris un pendu en Python
  Contenu : 6 messages, 1 fichier écrit (/pendu.py)
  Masqué  : 1 texte avec des données sensibles
  Toute personne qui a le lien pourra le lire, sans compte. /unshare pour le fermer.
Confirmer ? [y] oui  [n] non  y
✓ Lien public de la session #15 : http://localhost:8080/s/Xb3kQ9fL…
  1 texte masqué (données sensibles).
  /unshare Xb3kQ9fL pour le fermer.
> /shares
> /unshare Xb3kQ9fL
```

Tests : `tests/test_export.py`, `tests/test_web.py`.
