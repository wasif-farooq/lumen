"""Changes to the user's files: each one pauses for the user's approval (LangGraph interrupt)."""

from langchain_core.tools import tool
from langgraph.types import interrupt

from ... import fileops


def build(ctx) -> dict:
    last_results, emit, resolve = ctx.last_results, ctx.emit, ctx.resolve

    def _approved(plan: dict) -> str:
        """Ask the user, then do it. Re-running after resume repeats the checks, not the change."""
        decision = interrupt({"type": "approval", **{k: v for k, v in plan.items() if k != "content"}})
        if not (decision or {}).get("approved"):
            emit({"type": "action_cancelled", "summary": plan["summary"]})
            return (f"CANCELLED by the user: {plan['summary']}. Nothing changed. Tell the user it was cancelled; "
                    "do not ask them to approve it again.")
        try:
            done = fileops.execute(plan)
        except (fileops.FileOpError, OSError) as e:
            emit({"type": "action_failed", "summary": plan["summary"], "error": str(e)})
            return f"Failed: {e}"
        emit({"type": "action_done", **{k: v for k, v in done.items() if k != "content"}})
        if done.get("dst"):
            last_results[:] = [done["dst"]]
        return done["message"]

    def _plan(fn, *args) -> str:
        try:
            return _approved(fn(*args))
        except fileops.FileOpError as e:
            return f"Can't do that: {e}"

    @tool
    def create_folder(path: str) -> str:
        """Create a new folder (asks the user to approve first).

        Args:
            path: full path of the new folder, inside the user's folders, e.g. "~/Documents/Taxes 2026".
        """
        return _plan(fileops.plan_create_folder, path)

    @tool
    def create_file(path: str, content: str) -> str:
        """Create a new small TEXT file with the given content (asks the user to approve first).
        Never overwrites an existing file.

        Args:
            path: full path of the new file, e.g. "~/Documents/notes/todo.txt".
            content: the text to write.
        """
        return _plan(fileops.plan_create_file, path, content)

    @tool
    def copy_file(source: str, destination: str) -> str:
        """Copy a file or a whole folder (asks the user to approve first). Never overwrites.

        Args:
            source: full path, or a result number from the last results (e.g. "1").
            destination: a folder to copy into, or the full new path.
        """
        return _plan(fileops.plan_copy, str(resolve(source)), destination)

    @tool
    def move_file(source: str, destination: str) -> str:
        """Move or rename a file or folder (asks the user to approve first). Never overwrites.
        To rename, give the same folder with the new name.

        Args:
            source: full path, or a result number from the last results (e.g. "1").
            destination: a folder to move into, or the full new path (new name).
        """
        return _plan(fileops.plan_move, str(resolve(source)), destination)

    return {"create_folder": create_folder, "create_file": create_file, "copy_file": copy_file, "move_file": move_file}
