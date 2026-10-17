"""Text files for the viewer, a piece at a time, so a huge log opens at once and loads as you scroll."""

import codecs
from pathlib import Path

from ..core import errors

PIECE = 256 * 1024  # bytes per piece
MAX_PIECE = 1024 * 1024


def piece(p: Path, offset: int = 0, limit: int = PIECE) -> dict:
    """The text from byte `offset` on (about `limit` bytes, never cutting a character in two) and
    where the next piece starts; `done` when the file ends there."""
    size = p.stat().st_size
    limit = max(1024, min(limit, MAX_PIECE))
    if not 0 <= offset <= size:
        raise errors.InvalidInput("That part of the file doesn't exist.")
    with p.open("rb") as f:
        if offset == 0 and b"\x00" in f.read(4096):
            raise errors.InvalidInput("This file isn't text.", "Open it with its own program.")
        f.seek(offset)
        raw = f.read(limit)
    if offset > 0:  # don't start inside a character: skip UTF-8 continuation bytes
        skip = 0
        while skip < len(raw) and skip < 4 and raw[skip] & 0xC0 == 0x80:
            skip += 1
        raw, offset = raw[skip:], offset + skip
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    text = decoder.decode(raw)  # an incomplete character at the end waits for the next piece
    pending = len(decoder.getstate()[0])
    end = offset + len(raw) - pending
    return {"offset": offset, "next": end, "size": size, "done": end >= size, "text": text}
