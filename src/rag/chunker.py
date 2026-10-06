##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## Chunker: cut a text file into passages a search can return and a model can read
##
from dataclasses import dataclass

# A passage is about this long: enough to hold a whole function or a section, short enough that four of them
# fit in the room a tool result may take (app/context_window.py) and that the embedding model reads all of it
MAX_CHARS: int = 1500
# Lines repeated at the start of the next passage, so a sentence or a signature cut in two is whole in one of them
OVERLAP_LINES: int = 3

@dataclass(frozen=True, slots=True)
class Chunk:
    """ A passage of a file: its lines (from 1, both included) and its text, indentation kept """
    start: int
    end  : int
    text : str

def split(text: str) -> list[Chunk]:
    """
        Cut a text into passages of MAX_CHARS at most (a longer line makes a longer one), at a blank line when there
        is one in the second half of the passage: between two functions, two paragraphs, rather than in the middle
    """
    lines: list[str] = text.splitlines()
    chunks: list[Chunk] = []
    start: int = 0
    while start < len(lines):
        end: int = start
        size: int = 0
        while end < len(lines) and (end == start or size + len(lines[end]) + 1 <= MAX_CHARS):
            size += len(lines[end]) + 1
            end += 1
        if end < len(lines):
            # The last blank line of the second half: the passage stops there
            middle: int = start + (end - start) // 2
            end = next((cut for cut in range(end, middle, -1) if not lines[cut - 1].strip()), end)

        first, last = start, end
        while first < last and not lines[first].strip():
            first += 1
        while last > first and not lines[last - 1].strip():
            last -= 1
        if first < last:
            chunks.append(Chunk(first + 1, last, "\n".join(lines[first:last])))

        if end >= len(lines):
            break
        start = max(end - OVERLAP_LINES, start + 1)
    return chunks
