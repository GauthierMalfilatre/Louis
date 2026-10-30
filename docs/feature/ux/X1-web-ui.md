# X1 · Interface web

`louis --web` ouvre Louis dans le navigateur au lieu du terminal. La page est une interface de plus sur le même bus d'événements : la logique de Louis ne change pas.

## Ce qu'il fait

- **Conversation en direct** : la réponse s'écrit au fil de l'eau ; chaque appel d'outil s'affiche pendant qu'il tourne, puis se résume en une phrase qui se déplie d'un clic.
- **Permissions et plans** depuis la page, avec le diff : `O` autoriser, `N` refuser, `T` toujours pour cet outil dans la session ; les plans de [A3](../orchestration/A3-human-in-the-loop.md) s'approuvent de la même façon.
- **Le bouton ■** arrête ce que Louis fait, comme Ctrl+C.
- **Ce que coûte une réponse** : tokens écrits, vitesse, premier token, chargement du modèle ; le remplissage du contexte en direct ; sous chaque recherche dans la base, les passages trouvés.
- **Sessions** (avec `--user`) : la barre de gauche les liste par titre, les cherche, en reprend une d'un clic ; « Nouvelle session » fait un `/clear`, avec le prompt système de ton choix.
- **Réglages** : boutons « Réflexion » (`/think`) et « Pas à pas » (`/react`) ; toutes les commandes `/` marchent, avec leur menu.
- **Accueil** selon l'heure, la dernière session et tes changements en cours dans git (écrit par le scribe).
- **Onglet caché** : son titre et son icône disent que Louis attend ta réponse ou qu'il a fini ; la cloche ajoute une notification du bureau.
- Sert aussi les liens publics de `/share` (`/s/<jeton>`, voir [X3](X3-export-publication.md)).

## Commandes

| Commande | Comment ça marche | À quoi ça sert |
| -------- | ----------------- | -------------- |
| `louis --web` | lance le serveur sur `127.0.0.1:8080` et affiche son adresse à ouvrir | utiliser Louis depuis le navigateur |
| `--port <n>` / `--host <adresse>` | change le port (0 : un libre) / l'adresse d'écoute | plusieurs Louis, ou l'ouvrir au réseau |
| `--user <nom>` | les sessions du profil dans la barre latérale | reprendre ses sessions d'un clic |
| `O` / `N` / `T` (ou `Y` / `N` / `A`) | autorise, refuse, toujours pour cet outil | répondre aux permissions et aux plans au clavier |
| bouton ■ | arrête ce que Louis fait, comme Ctrl+C | couper une réponse |
| boutons « Réflexion », « Pas à pas », cloche | `/think`, `/react`, notifications du bureau | régler sans taper de commande |
| `/…` | toutes les commandes du terminal, avec leur menu (flèches, Tab, Entrée) | tout faire depuis la page |

## Exemples

```bash
louis --web                          # http://127.0.0.1:8080
louis --web --port 9000 --user ada
louis --web --host 0.0.0.0           # ouvert au réseau, SANS mot de passe
```

Le serveur écoute sur `127.0.0.1` : ce poste seulement. Avec `--host 0.0.0.0`, qui l'atteint peut faire agir Louis sur tes fichiers. Ctrl+C dans le terminal arrête Louis.

Tests : `tests/test_web.py`.
