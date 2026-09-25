##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## The files the model has seen: an edit must rest on their content as it is now
##
import os

class SeenFiles:
    """
        The files the model has read or written in the current session, with their state then (modification time
        and size). edit_file needs one: its old_str must be copied from the file, not remembered or guessed, and a
        file changed since (by the user) must be read again
    """
    def __init__(self):
        """ Init the files seen: none yet """
        self.__seen: dict[str, tuple[int, int]] = {}

    @staticmethod
    def __stamp(path: str) -> tuple[int, int] | None:
        """ What tells that a file changed: its modification time and its size, None if it is gone """
        try:
            stat: os.stat_result = os.stat(path)
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def mark(self, path: str) -> None:
        """ The model knows this file (a full path) as it is now: it read it, or wrote it """
        stamp: tuple[int, int] | None = self.__stamp(path)
        if stamp is None:
            self.__seen.pop(path, None)
        else:
            self.__seen[path] = stamp

    def state(self, path: str) -> str:
        """ "seen", "unseen", or "changed": read, then modified by someone else """
        if path not in self.__seen:
            return "unseen"
        return "seen" if self.__stamp(path) == self.__seen[path] else "changed"

    def clear(self) -> None:
        """ Another session: the model has read nothing of it """
        self.__seen.clear()
