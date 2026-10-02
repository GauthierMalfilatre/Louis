from bootstrap.sources.tool.tools import Tool
import os
from bootstrap.sources.tool.paths import resolve_path, display_path

DEFAULT_DEPTH = 2
MAX_DEPTH = 6
MAX_ENTRIES = 200

IGNORED = {
    ".git", ".hg", ".svn", ".idea", ".vscode",
    "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache",
    "build", "dist", "target", "out", "cmake-build-debug", "cmake-build-release",
}
IGNORED_EXT = {".o", ".obj", ".a", ".so", ".dll", ".exe", ".pyc", ".class"}


class TreeTool(Tool):
    def __init__(self):
        super().__init__(
            "tree",
            "Affiche l'arborescence d'un dossier (dossiers d'abord, suffixés par '/'). "
            "Les dossiers de build, de dépendances et .git sont ignorés. "
            "Commence avec une petite profondeur, puis explore les sous-dossiers intéressants.",
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Dossier à afficher, relatif au dossier courant (défaut : '.')"
                    },
                    "depth": {
                        "type": "integer",
                        "description": f"Profondeur maximale (défaut : {DEFAULT_DEPTH}, max : {MAX_DEPTH})"
                    }
                },
                "required": []
            }
        )

    def handler(self, manager, **kwargs) -> str:
        """Print a bounded directory tree."""
        path = kwargs.get("path") or "."
        try:
            depth = int(kwargs.get("depth", DEFAULT_DEPTH))
        except (TypeError, ValueError):
            depth = DEFAULT_DEPTH
        depth = max(1, min(depth, MAX_DEPTH))

        full = resolve_path(manager, path)
        if full is None:
            return f"Erreur : '{path}' est en dehors du projet."
        if not os.path.exists(full):
            return f"Erreur : '{path}' n'existe pas."
        if not os.path.isdir(full):
            return f"Erreur : '{path}' n'est pas un dossier."

        manager.stream.debug(f"\n>>> tree: {full} (depth={depth})\n")

        root = display_path(full)
        lines = [root if root.endswith("/") else root + "/"]
        stats = {"shown": 0, "hidden": 0, "truncated_dirs": 0}
        self._walk(full, "", 1, depth, lines, stats)

        if stats["hidden"]:
            lines.append(f"\n… {stats['hidden']} entrées de plus non affichées "
                        f"(limite de {MAX_ENTRIES}). Utilise un depth plus faible "
                        "ou un sous-dossier.")
        elif stats["truncated_dirs"]:
            lines.append(f"\n({stats['truncated_dirs']} dossiers non développés : "
                        "augmente depth ou appelle tree sur un sous-dossier.)")

        res = "\n".join(lines)
        manager.stream.debug(f"---\n{res}\n---\n")
        return res

    def _walk(self, dir_path, prefix, level, depth, lines, stats):
        try:
            entries = list(os.scandir(dir_path))
        except OSError as e:
            lines.append(f"{prefix}└── [erreur : {e.strerror}]")
            return

        entries = [
            e for e in entries
            if not (e.is_dir(follow_symlinks=False) and e.name in IGNORED)
            and os.path.splitext(e.name)[1] not in IGNORED_EXT
        ]
        # dossiers d'abord, puis ordre alphabétique insensible à la casse
        entries.sort(key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower()))

        for i, entry in enumerate(entries):
            if stats["shown"] >= MAX_ENTRIES:
                stats["hidden"] += len(entries) - i
                return

            last = i == len(entries) - 1
            branch = "└── " if last else "├── "
            is_dir = entry.is_dir(follow_symlinks=False)
            name = entry.name + ("/" if is_dir else "")
            if entry.is_symlink():
                name += " -> (lien)"

            lines.append(prefix + branch + name)
            stats["shown"] += 1

            if is_dir:
                if level < depth:
                    self._walk(entry.path, prefix + ("    " if last else "│   "),
                            level + 1, depth, lines, stats)
                else:
                    stats["truncated_dirs"] += 1