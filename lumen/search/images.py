"""Visual search: CLIP image/text signatures (ONNX on CPU).

- search by description: "sunset at the beach" matches what images look like, not only their caption
- similar images: by path or by an uploaded photo
"""

import sqlite3
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from ..core.settings import settings
from ..indexing import power

if TYPE_CHECKING:
    from PIL import Image

REPO = "Xenova/clip-vit-base-patch32"  # quantized ONNX build of OpenAI CLIP ViT-B/32
# Searching pictures by words: minimum CLIP score, and how far below the best match still counts
TEXT_FLOOR, TEXT_SPREAD = 0.26, 0.025
FILES = ["onnx/vision_model_quantized.onnx", "onnx/text_model_quantized.onnx", "tokenizer.json"]
MIN_BYTES = 2 * 1024  # skip tiny icons
MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32).reshape(3, 1, 1)
STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32).reshape(3, 1, 1)

_models = {}


def _model_dir() -> Path:
    return settings.data_dir / "models" / "clip"


def _load() -> dict:
    if _models:
        return _models
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    paths = {f: hf_hub_download(REPO, f, local_dir=str(_model_dir())) for f in FILES}
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = power.threads()
    opts.inter_op_num_threads = 1
    _models["vision"] = ort.InferenceSession(paths[FILES[0]], opts, providers=["CPUExecutionProvider"])
    _models["text"] = ort.InferenceSession(paths[FILES[1]], opts, providers=["CPUExecutionProvider"])
    _models["tok"] = Tokenizer.from_file(paths[FILES[2]])
    return _models


def _normalize(v: np.ndarray) -> np.ndarray:
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-8)


def _pixels(im: "Image.Image") -> np.ndarray:
    """CLIP preprocessing: shortest side 224 (bicubic), center crop 224, scale, normalize, CHW."""
    from PIL import Image

    im = im.convert("RGB")
    w, h = im.size
    s = 224 / min(w, h)
    im = im.resize((max(224, round(w * s)), max(224, round(h * s))), Image.Resampling.BICUBIC)
    w, h = im.size
    left, top = (w - 224) // 2, (h - 224) // 2
    im = im.crop((left, top, left + 224, top + 224))
    x = np.asarray(im, dtype=np.float32).transpose(2, 0, 1) / 255.0
    return (x - MEAN) / STD


def embed_images(images: list) -> np.ndarray:
    m = _load()
    batch = np.stack([_pixels(im) for im in images]).astype(np.float32)
    return _normalize(m["vision"].run(None, {"pixel_values": batch})[0])


def embed_text(text: str) -> np.ndarray:
    m = _load()
    ids = m["tok"].encode(text.strip()[:300]).ids[:77]
    out = m["text"].run(None, {"input_ids": np.array([ids], dtype=np.int64)})[0]
    return _normalize(out)[0]


def open_image(source: str | bytes) -> "Image.Image":
    """PIL image from a path (any format we caption) or raw bytes, downscaled for speed."""
    from PIL import Image

    if isinstance(source, (bytes, bytearray)):
        im = Image.open(BytesIO(source))
    else:
        from ..indexing.passes.captions import _render

        im = Image.open(BytesIO(_render(source)))
    im.load()
    return im


# ---------- search ----------

_cache: dict[str, Any] = {"key": None}


def _matrix(conn: sqlite3.Connection) -> tuple[list[dict], np.ndarray]:
    """All image signatures as one matrix (cached until the set of images changes)."""
    key = conn.execute(
        "SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(SUM(LENGTH(embedding)), 0) FROM files WHERE visual_done=1"
    ).fetchone()
    key = tuple(key)
    if _cache["key"] != key:
        rows = conn.execute(
            "SELECT id, path, name, ext, size, mtime, embedding FROM files WHERE visual_done=1 ORDER BY id"
        ).fetchall()
        _cache.update(
            key=key,
            rows=[dict(r) for r in rows],
            vecs=np.stack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
            if rows
            else np.zeros((0, 512), np.float32),
        )
    return _cache["rows"], _cache["vecs"]


def _top(
    conn: sqlite3.Connection, vec: np.ndarray, k: int, floor: float, folder: str = "", skip: str = ""
) -> list[tuple[dict, float]]:
    rows, vecs = _matrix(conn)
    if not rows:
        return []
    sims = vecs @ vec
    out = []
    for i in np.argsort(-sims):
        r = rows[i]
        if sims[i] < floor:
            break
        if r["path"] == skip or (folder and folder not in r["path"]):
            continue
        out.append((r, float(sims[i])))
        if len(out) >= k:
            break
    return out


def search_text(conn: sqlite3.Connection, description: str, k: int = 12, folder: str = "") -> list[tuple[dict, float]]:
    # CLIP text-image scores are small and close together: for your images a real match scored
    # ~0.28-0.30 while "a cat" (no cats) still scored 0.24. Keep only clear matches near the best one.
    found = _top(conn, embed_text(f"a photo of {description}"), k, floor=TEXT_FLOOR, folder=folder)
    return [(r, s) for r, s in found if s >= found[0][1] - TEXT_SPREAD] if found else []


def similar_to(
    conn: sqlite3.Connection, source: str | bytes, k: int = 12, folder: str = ""
) -> list[tuple[dict, float]]:
    """source: an indexed image path, or raw image bytes (an uploaded photo)."""
    skip = ""
    if isinstance(source, str):
        row = conn.execute("SELECT embedding FROM files WHERE path=? AND visual_done=1", (source,)).fetchone()
        vec = np.frombuffer(row["embedding"], dtype=np.float32) if row else embed_images([open_image(source)])[0]
        skip = source
    else:
        vec = embed_images([open_image(source)])[0]
    # Image-image scores run high: half of all pairs in your images score >= 0.55, so a low floor
    # returned 12 unrelated pictures every time (a scan of fingerprints: its copy 0.98, then filler
    # at 0.65-0.69). Keep only strong matches near the best one.
    found = _top(conn, vec, k, floor=0.8, folder=folder, skip=skip)
    return [(r, s) for r, s in found if s >= found[0][1] - 0.1] if found else []
