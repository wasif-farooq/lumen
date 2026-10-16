"""Image signatures (CLIP) for every new image, so pictures can be found by what they show and
by looking alike. Batches of 8; skipped on battery like the other AI passes."""

import time

import numpy as np

from ...core.filetypes import IMAGE_EXTS
from ...search import images
from .. import power


def process_pending(conn, progress=None) -> dict:
    """Signature + fingerprints for every image that has none yet. Batches of 8, power-aware."""
    rows = conn.execute(
        f"SELECT id, path, size FROM files WHERE visual_done IS NULL AND ext IN ({','.join('?' * len(IMAGE_EXTS))})",
        sorted(IMAGE_EXTS),
    ).fetchall()
    stats = {"images": 0, "failed": 0, "skipped": 0, "seconds": 0.0}
    started = time.time()
    small = [r["id"] for r in rows if r["size"] < images.MIN_BYTES]
    conn.executemany("UPDATE files SET visual_done=0 WHERE id=?", [(i,) for i in small])
    stats["skipped"] = len(small)
    todo = [r for r in rows if r["size"] >= images.MIN_BYTES]
    if todo:
        try:
            images._load()
        except Exception as e:
            return {"error": f"image model could not be loaded ({e}); left for next run"}
    for start in range(0, len(todo), 8):
        allowed, why = power.heavy_allowed()
        if not allowed:
            stats["stopped"] = f"stopped: {why}; {len(todo) - start} left for next run"
            break
        power.wait_until_idle()
        batch, pictures = [], []
        for r in todo[start:start + 8]:
            try:
                im = images.open_image(r["path"])
                pictures.append(im)
                batch.append(r)
            except Exception:
                conn.execute("UPDATE files SET visual_done=0 WHERE id=?", (r["id"],))
                stats["failed"] += 1
        if pictures:
            vecs = images.embed_images(pictures).astype(np.float32)
            for r, vec in zip(batch, vecs):
                conn.execute("UPDATE files SET embedding=?, visual_done=1 WHERE id=?", (vec.tobytes(), r["id"]))
                stats["images"] += 1
        conn.commit()
        if progress:
            progress(min(start + 8, len(todo)), len(todo), todo[min(start + 7, len(todo) - 1)]["path"], "image signatures")
    stats["seconds"] = round(time.time() - started, 1)
    return stats
