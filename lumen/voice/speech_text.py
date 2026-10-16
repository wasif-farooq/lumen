"""Turning the agent's written answer into something to say: no markdown, file names instead of
full paths, and sentences short enough to start speaking quickly."""

import re

MAX_SENTENCE = 220  # longer sentences are split at a comma, so speech starts sooner


def speakable(text: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*|__|^#+\s*|^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"https?://\S+", "a link", text)
    # /home/alex/Documents/invoice-1042.pdf -> invoice-1042.pdf: nobody wants a path read aloud
    text = re.sub(r"(?:~|/)[^\s,;:()]*/([^\s/,;:()]+)", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def sentences(text: str) -> list[str]:
    """The answer as sentences to speak one by one (each starts playing while the next is made)."""
    out = []
    for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", speakable(text)):
        while len(s) > MAX_SENTENCE and "," in s[:MAX_SENTENCE]:
            cut = s.rindex(",", 0, MAX_SENTENCE) + 1
            out.append(s[:cut].strip())
            s = s[cut:].strip()
        if s:
            out.append(s)
    return out
