"""File changes the agent may make, always after the user approves: create a folder or text file,
copy or move (rename) a file or folder. Never deletes, never overwrites; every change can be undone.

    plan_*()  -> checks the request and describes it (nothing changes yet)
    execute() -> does it, logs it for undo, keeps the search index in step
    undo()    -> reverses one logged change
"""

from .actions import execute, undo
from .journal import history
from .plans import FileOpError, plan_copy, plan_create_file, plan_create_folder, plan_move

__all__ = [
    "FileOpError",
    "execute",
    "history",
    "plan_copy",
    "plan_create_file",
    "plan_create_folder",
    "plan_move",
    "undo",
]
