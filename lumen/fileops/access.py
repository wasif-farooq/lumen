"""Which paths Lumen may touch (only inside the indexed folders), and opening them on the desktop."""

import shutil
import subprocess
from pathlib import Path

from ..core.formatting import fmt_time
from ..core.settings import settings


def allowed(p: str) -> Path:
    path = Path(p).expanduser().resolve()
    if not any(path == r or path.is_relative_to(r) for r in settings.roots):
        raise PermissionError(f"{path} is outside the allowed folders: {', '.join(map(str, settings.roots))}")
    return path


def launch(target: Path, start: float = 0) -> str:
    cmd = ["xdg-open", str(target)]
    at = ""
    if start > 0 and settings.open_mode != "xdg":
        at = f" in the video player at {fmt_time(start)}"
    elif start > 0:
        at = f" at {fmt_time(start)}"
        if shutil.which("mpv"):
            cmd = ["mpv", "--force-window", f"--start={int(start)}", str(target)]
        elif shutil.which("vlc"):
            cmd = ["vlc", f"--start-time={int(start)}", str(target)]
        else:
            at = f" (no mpv/vlc to jump to {fmt_time(start)}; opened from the start)"
    if settings.open_mode != "xdg":
        return (
            f"NOT OPENED (test mode: running in Docker without a desktop). Would have opened: {target}{at}. "
            "Tell the user it was not opened and give the full path."
        )
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return f"Opened: {target}{at}"
