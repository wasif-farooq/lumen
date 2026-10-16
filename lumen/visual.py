"""Visual search: CLIP image/text signatures (ONNX on CPU), similar images and duplicates.

- search by description: "sunset at the beach" matches what images look like, not only their caption
- similar images: by path or by an uploaded photo
- duplicates: identical files (same bytes) and look-alikes (resized/recompressed copies)
"""

import hashlib
import time
from io import BytesIO

import numpy as np

from . import config, power

REPO = "Xenova/clip-vit-base-patch32"  # quantized ONNX build of OpenAI CLIP ViT-B/32
FILES = ["onnx/vision_model_quantized.onnx", "onnx/text_model_quantized.onnx", "tokenizer.json"]
MIN_BYTES = 2 * 1024  # skip tiny icons
MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32).reshape(3, 1, 1)
STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32).reshape(3, 1, 1)

# Look-alike candidates (cheap): near-identical fingerprint AND near-identical CLIP signature.
LOOKALIKE_HASH_BITS = 6
LOOKALIKE_COSINE = 0.965
# Candidates are then verified on pixels, because screenshots of the same screen pass both cheap
# tests while showing different content (see _same_picture).
LOSSLESS = {"png", "bmp", "tif", "tiff", "gif"}
MAX_LOCAL_DIFF = 28  # 99th-percentile pixel difference (0-255) allowed for resized/recompressed copies

_models = {}


def _model_dir():
    return config.DATA_DIR / "models" / "clip"


def _load():
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


def _pixels(im) -> np.ndarray:
    """CLIP preprocessing: shortest side 224 (bicubic), center crop 224, scale, normalize, CHW."""
    from PIL import Image

    im = im.convert("RGB")
    w, h = im.size
    s = 224 / min(w, h)
    im = im.resize((max(224, round(w * s)), max(224, round(h * s))), Image.BICUBIC)
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


def dhash(im) -> int:
    """64-bit difference hash: survives resizing and recompression, changes with real edits."""
    from PIL import Image

    g = np.asarray(im.convert("L").resize((9, 8), Image.LANCZOS), dtype=np.int16)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    value = int("".join("1" if b else "0" for b in bits), 2)
    return value - (1 << 64) if value >= (1 << 63) else value  # fits SQLite's signed INTEGER


def file_sha1(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def open_image(source):
    """PIL image from a path (any format we caption) or raw bytes, downscaled for speed."""
    from PIL import Image

    if isinstance(source, (bytes, bytearray)):
        im = Image.open(BytesIO(source))
    else:
        from .caption import _render

        im = Image.open(BytesIO(_render(source)))
    im.load()
    return im


# ---------- indexing pass ----------

def process_pending(conn, progress=None) -> dict:
    """Signature + fingerprints for every image that has none yet. Batches of 8, power-aware."""
    from .caption import IMAGE_EXTS

    rows = conn.execute(
        f"SELECT id, path, size FROM files WHERE visual_done IS NULL AND ext IN ({','.join('?' * len(IMAGE_EXTS))})",
        sorted(IMAGE_EXTS),
    ).fetchall()
    stats = {"images": 0, "failed": 0, "skipped": 0, "seconds": 0.0}
    started = time.time()
    small = [r["id"] for r in rows if r["size"] < MIN_BYTES]
    conn.executemany("UPDATE files SET visual_done=0 WHERE id=?", [(i,) for i in small])
    stats["skipped"] = len(small)
    todo = [r for r in rows if r["size"] >= MIN_BYTES]
    if todo:
        try:
            _load()
        except Exception as e:
            return {"error": f"image model could not be loaded ({e}); left for next run"}
    for start in range(0, len(todo), 8):
        allowed, why = power.heavy_allowed()
        if not allowed:
            stats["stopped"] = f"stopped: {why}; {len(todo) - start} left for next run"
            break
        power.wait_until_idle()
        batch, images = [], []
        for r in todo[start:start + 8]:
            try:
                im = open_image(r["path"])
                images.append(im)
                batch.append((r, dhash(im), file_sha1(r["path"])))
            except Exception:
                conn.execute("UPDATE files SET visual_done=0 WHERE id=?", (r["id"],))
                stats["failed"] += 1
        if images:
            vecs = embed_images(images).astype(np.float32)
            for (r, dh, sha), vec in zip(batch, vecs):
                conn.execute(
                    "UPDATE files SET embedding=?, dhash=?, sha1=?, visual_done=1 WHERE id=?",
                    (vec.tobytes(), dh, sha, r["id"]),
                )
                stats["images"] += 1
        conn.commit()
        if progress:
            progress(min(start + 8, len(todo)), len(todo), todo[min(start + 7, len(todo) - 1)]["path"], "image signatures")
    stats["seconds"] = round(time.time() - started, 1)
    return stats


# ---------- search ----------

_cache = {"key": None}


def _matrix(conn):
    """All image signatures as one matrix (cached until the set of images changes)."""
    key = conn.execute("SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(SUM(LENGTH(embedding)), 0) FROM files WHERE visual_done=1").fetchone()
    key = tuple(key)
    if _cache["key"] != key:
        rows = conn.execute(
            "SELECT id, path, name, ext, size, mtime, embedding, dhash, sha1 FROM files WHERE visual_done=1 ORDER BY id"
        ).fetchall()
        _cache.update(
            key=key,
            rows=[dict(r) for r in rows],
            vecs=np.stack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows]) if rows else np.zeros((0, 512), np.float32),
        )
    return _cache["rows"], _cache["vecs"]


def _top(conn, vec: np.ndarray, k: int, floor: float, folder: str = "", skip: str = "") -> list[tuple[dict, float]]:
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


def search_text(conn, description: str, k: int = 12, folder: str = "") -> list[tuple[dict, float]]:
    # CLIP text-image scores are small and close together: for your images a real match scored
    # ~0.28-0.30 while "a cat" (no cats) still scored 0.24. Keep only clear matches near the best one.
    found = _top(conn, embed_text(f"a photo of {description}"), k, floor=0.26, folder=folder)
    return [(r, s) for r, s in found if s >= found[0][1] - 0.025] if found else []


def similar_to(conn, source, k: int = 12, folder: str = "") -> list[tuple[dict, float]]:
    """source: an indexed image path, or raw image bytes (an uploaded photo)."""
    skip = ""
    if isinstance(source, str):
        row = conn.execute("SELECT embedding FROM files WHERE path=? AND visual_done=1", (source,)).fetchone()
        vec = np.frombuffer(row["embedding"], dtype=np.float32) if row else embed_images([open_image(source)])[0]
        skip = source
    else:
        vec = embed_images([open_image(source)])[0]
    return _top(conn, vec, k, floor=0.6, folder=folder, skip=skip)


def _same_picture(a: dict, b: dict, cache: dict) -> bool:
    """Is b the same picture as a, just saved differently (resized, recompressed, other format)?

    - two lossless files of the same size: only if every pixel matches (a changed pixel = new content)
    - otherwise: copies differ a little everywhere, edits differ a lot in one area, so compare the
      99th-percentile difference rather than the average
    """
    from PIL import Image

    def load(f):
        if f["path"] not in cache:
            with Image.open(f["path"]) as im:
                im.load()
                cache[f["path"]] = im.convert("RGB")
        return cache[f["path"]]

    try:
        ia, ib = load(a), load(b)
    except Exception:
        return False
    if ia.size == ib.size and a["ext"] in LOSSLESS and b["ext"] in LOSSLESS:
        return np.array_equal(np.asarray(ia), np.asarray(ib))
    ga = np.asarray(ia.convert("L").resize((128, 128), Image.LANCZOS), dtype=np.float32)
    gb = np.asarray(ib.convert("L").resize((128, 128), Image.LANCZOS), dtype=np.float32)
    return float(np.percentile(np.abs(ga - gb), 99)) <= MAX_LOCAL_DIFF


_dup_cache: dict = {}


def duplicates(conn, folder: str = "") -> list[dict]:
    """Groups of identical files (same bytes) or look-alikes (same picture resized/recompressed).
    Cached until the set of indexed images changes."""
    _matrix(conn)
    key = (_cache["key"], folder)
    if key not in _dup_cache:
        _dup_cache.clear()
        _dup_cache[key] = _find_duplicates(conn, folder)
    return _dup_cache[key]


def _find_duplicates(conn, folder: str) -> list[dict]:
    rows, vecs = _matrix(conn)
    idx = [i for i, r in enumerate(rows) if not folder or folder in r["path"]]
    parent = {i: i for i in idx}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        parent[find(a)] = find(b)

    by_sha = {}
    for i in idx:
        by_sha.setdefault(rows[i]["sha1"], []).append(i)
    for group in by_sha.values():
        for j in group[1:]:
            union(group[0], j)
    hashes = np.array([rows[i]["dhash"] & 0xFFFFFFFFFFFFFFFF for i in idx], dtype=np.uint64)
    pixels: dict = {}
    sub = vecs[idx] if idx else vecs
    for a in range(len(idx)):
        # look-alike: near-identical fingerprint AND very similar content (both, to avoid false pairs)
        x = np.bitwise_xor(hashes[a + 1:], hashes[a])
        bits = np.array([int(v).bit_count() for v in x]) if len(x) else np.array([])
        close = np.nonzero(bits <= LOOKALIKE_HASH_BITS)[0]
        if len(close):
            sims = sub[a + 1 + close] @ sub[a]
            for c, s in zip(close, sims):
                ia, ib = idx[a], idx[a + 1 + c]
                if s >= LOOKALIKE_COSINE and find(ia) != find(ib) and _same_picture(rows[ia], rows[ib], pixels):
                    union(ia, ib)

    groups = {}
    for i in idx:
        groups.setdefault(find(i), []).append(i)
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        files = sorted((rows[i] for i in members), key=lambda r: (r["mtime"], r["path"]))
        identical = len({f["sha1"] for f in files}) == 1
        keep = max(files, key=lambda f: f["size"]) if not identical else files[0]
        out.append({
            "kind": "identical" if identical else "lookalike",
            "files": [{k: f[k] for k in ("path", "name", "ext", "size", "mtime")} for f in files],
            "keep": keep["path"],  # oldest identical copy, or the largest look-alike (best quality)
            "reclaimable": sum(f["size"] for f in files if f["path"] != keep["path"]),
        })
    out.sort(key=lambda g: -g["reclaimable"])
    return out
