"""Sizes and times written the way people read them."""


def human_size(n: float) -> str:
    """1536 -> "1.5 KB"."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_time(seconds: float) -> str:
    """605 -> "10:05", 3725 -> "1:02:05"."""
    s = int(seconds)
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
