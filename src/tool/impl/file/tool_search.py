##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Search tool: find the lines matching a regex in the files of the project
##
from tool.tool import Tool
from tool.impl.file.tool_tree import IGNORED, IGNORED_EXT
from utils.path import resolve_path, display_path
from logger.logger import LOG_FILE
import fnmatch
import os
import re

DEFAULT_RESULTS = 50
MAX_RESULTS = 200
MAX_FILE_SIZE = 1_000_000
MAX_LINE_LEN = 300

class SearchTool(Tool):
    def __init__(self):
        super().__init__(
            "search",
            "Cherche une expression régulière dans les fichiers texte du projet, et renvoie chaque "
            "ligne trouvée sous la forme 'chemin:ligne: contenu'. Utilise-le pour trouver où une "
            "fonction, une classe ou un texte est défini ou utilisé, puis lis seulement ces lignes "
            "avec cat_file (start_line et end_line). Les dossiers de build, de dépendances et .git "
            "sont ignorés. Commence le motif par (?i) pour ignorer la casse.",
            {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Expression régulière à chercher (syntaxe Python)"
                    },
                    "path": {
                        "type": "string",
                        "description": "Dossier ou fichier où chercher, relatif au dossier courant (défaut : '.')"
                    },
                    "glob": {
                        "type": "string",
                        "description": "Ne cherche que dans les fichiers dont le nom correspond, par exemple '*.py'"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": f"Nombre maximum de lignes renvoyées (défaut : {DEFAULT_RESULTS}, max : {MAX_RESULTS})"
                    }
                },
                "required": ["pattern"]
            }
        )

    def handle(self, app, **kwargs) -> str:
        """Find the lines matching a regex, in a file or in every file of a folder."""
        pattern = kwargs.get("pattern")
        path = kwargs.get("path") or "."
        glob = kwargs.get("glob") or None
        if not isinstance(pattern, str) or not pattern:
            return "Erreur : 'pattern' est requis."
        if not isinstance(path, str) or not (glob is None or isinstance(glob, str)):
            return "Erreur : 'path' et 'glob' doivent être du texte."
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Erreur : expression régulière invalide ({e})."
        try:
            limit = int(kwargs.get("max_results") or DEFAULT_RESULTS)
        except (TypeError, ValueError):
            limit = DEFAULT_RESULTS
        limit = max(1, min(limit, MAX_RESULTS))

        full = resolve_path(app, path)
        if full is None:
            return f"Erreur : '{path}' est en dehors du projet."
        if not os.path.exists(full):
            return f"Erreur : '{path}' n'existe pas."

        found = []
        total = 0
        for file in self._files(full, glob):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for number, line in enumerate(lines, 1):
                if not regex.search(line):
                    continue
                total += 1
                if len(found) < limit:
                    line = line.strip()
                    if len(line) > MAX_LINE_LEN:
                        line = line[:MAX_LINE_LEN] + " …[ligne tronquée]"
                    found.append(f"{display_path(file)}:{number}: {line}")

        if not found:
            where = f" dans les fichiers {glob}" if glob else ""
            return f"Aucun résultat pour '{pattern}' dans {display_path(full)}{where}."
        res = "\n".join(found)
        if total > len(found):
            res += (f"\n… {total - len(found)} résultats de plus non affichés. "
                    "Affine le motif, le dossier ou le glob.")
        return res

    def _files(self, full, glob):
        """The regular files to search, in order: links, ignored folders and big files left out."""
        if os.path.isfile(full):
            yield full
            return
        # os.walk does not go down into links to folders: nothing outside the project is reached
        for root, dirs, files in os.walk(full):
            dirs[:] = sorted(d for d in dirs if d not in IGNORED)
            for name in sorted(files):
                file = os.path.join(root, name)
                if (os.path.islink(file) or not os.path.isfile(file)
                        or os.path.splitext(name)[1] in IGNORED_EXT or name == LOG_FILE
                        or (glob and not fnmatch.fnmatch(name, glob))
                        or os.path.getsize(file) > MAX_FILE_SIZE):
                    continue
                yield file
