"""The tools the agent can call. All of them are limited to the indexed folders."""

from . import changes, files, images, search
from .context import ToolContext

# The order the model sees them in
ORDER = [
    "search_files",
    "find_in_files",
    "read_file",
    "search_images",
    "find_similar_images",
    "list_dir",
    "open_file",
    "show_in_folder",
    "create_folder",
    "create_file",
    "copy_file",
    "move_file",
]


def make_tools(emit=None, app: bool = False, state: dict | None = None) -> list:
    """The tool set for one chat session (see ToolContext for emit and state)."""
    ctx = ToolContext(emit, app, state)
    tools = {}
    for module in (search, images, files, changes):
        tools.update(module.build(ctx))
    return [tools[name] for name in ORDER]
