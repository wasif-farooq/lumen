"""What a folder's .gitignore files leave out, read the way git reads them: each .gitignore applies
to its folder and everything below it, deeper files override higher ones, `!` brings a path
back, and a pattern with a slash is anchored to the .gitignore's folder."""

import logging
import os

from pathspec import GitIgnoreSpec

log = logging.getLogger(__name__)

# The .gitignore files that apply in one folder: (the folder each one is in, its rules), top first
Rules = tuple[tuple[str, GitIgnoreSpec], ...]


def rules_for(folder: str, inherited: Rules) -> Rules:
    """The rules for `folder`: its parent's, plus its own .gitignore if it has one."""
    path = os.path.join(folder, ".gitignore")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            spec = GitIgnoreSpec.from_lines(f)
    except FileNotFoundError:
        return inherited
    except OSError as e:  # unreadable: index the folder as if it had none
        log.debug("can't read %s: %s", path, e)
        return inherited
    return (*inherited, (folder, spec))


def ignored(path: str, is_dir: bool, rules: Rules) -> bool:
    """Whether git would ignore this file or folder. The deepest rule that matches decides."""
    decision = None
    for base, spec in rules:
        rel = os.path.relpath(path, base) + ("/" if is_dir else "")
        result = spec.check_file(rel).include
        if result is not None:
            decision = result
    return bool(decision)
