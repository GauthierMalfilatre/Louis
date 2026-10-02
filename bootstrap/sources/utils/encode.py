import base64
from pathlib import Path

def encodePicture(path: str | Path) -> str:
    """ Encode an image """
    return base64.b64encode(Path(path).read_bytes()).decode()
