"""Files only this user may read (API keys, paired devices): created that way from the start,
so they are never readable by others, not even for a moment."""

import json
import os
from pathlib import Path


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(data, out, indent=1)
    os.chmod(path, 0o600)  # an existing file keeps its old mode on open(): set it again
