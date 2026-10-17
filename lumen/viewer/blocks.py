"""Documents for the viewer as blocks: headings, paragraphs, tables, and slide / sheet / chapter
breaks. Built from the same readers as indexing (lumen.indexing.extract and office), so what
search found is what the viewer shows.

    {"type": "heading", "text": "Budget", "level": 1}
    {"type": "paragraph", "text": "..."}
    {"type": "table", "rows": [["Item", "Cost"], ["Travel", "1200"]]}
    {"type": "break", "label": "Slide 3"}
"""

import csv
from collections.abc import Iterable, Iterator
from pathlib import Path

from ..core import limits
from ..indexing import office

MAX_CHARS = 5_000_000  # a document's text shown at most (the rest: "showing the first …")
MAX_ROWS = 5000  # rows of one table


def blocks(p: Path, ext: str) -> dict:
    """{"blocks": [...], "cut": bool}; "cut" when the document was longer than shown."""
    if ext in ("docx",):
        parts: Iterable[dict] = _docx(p)
    elif ext in ("csv", "tsv"):
        parts = _csv(p, "\t" if ext == "tsv" else ",")
    elif ext == "xlsx":
        parts = _from_pieces(office.xlsx(p), breaks=("Sheet: ",))
    elif ext == "pptx":
        parts = _from_pieces(office.pptx(p), breaks=("Slide ",), notes=True)
    elif ext in ("odt", "ods", "odp"):
        parts = _from_pieces(office.odf(p))
    elif ext == "epub":
        parts = _chapters(office.epub(p))
    else:
        return {"blocks": [], "cut": False}
    if ext in ("docx", "xlsx", "pptx", "odt", "ods", "odp", "epub") and p.stat().st_size > limits.MAX_ZIPPED_BYTES:
        return {"blocks": [{"type": "paragraph", "text": "This document is too big to show here."}], "cut": True}
    out, total, cut = [], 0, False
    for b in parts:
        total += sum(len(c) for row in b.get("rows", []) for c in row) + len(b.get("text", ""))
        if total > MAX_CHARS:
            cut = True
            break
        out.append(b)
    return {"blocks": out, "cut": cut}


def _from_pieces(pieces: Iterable[str], breaks: tuple[str, ...] = (), notes: bool = False) -> Iterator[dict]:
    """The indexing readers' pieces: " | " rows grouped into tables, break markers, paragraphs."""
    rows: list[list[str]] = []
    for piece in pieces:
        if " | " in piece and not any(piece.startswith(b) for b in breaks):
            if len(rows) < MAX_ROWS:
                rows.append([c.strip() for c in piece.split(" | ")])
            continue
        if rows:
            yield {"type": "table", "rows": _square(rows)}
            rows = []
        if any(piece.startswith(b) for b in breaks) and len(piece) < 200:
            yield {"type": "break", "label": piece.removeprefix("Sheet: ")}
        elif notes and piece.startswith("Notes: "):
            yield {"type": "paragraph", "text": piece, "style": "notes"}
        elif piece.strip():
            yield {"type": "paragraph", "text": piece.strip()}
    if rows:
        yield {"type": "table", "rows": _square(rows)}


def _square(rows: list[list[str]]) -> list[list[str]]:
    """Every row as wide as the widest, so columns line up."""
    width = max(len(r) for r in rows)
    return [r + [""] * (width - len(r)) for r in rows]


def _docx(p: Path) -> Iterator[dict]:
    """Paragraphs, headings and tables in the order they are in the document."""
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = docx.Document(str(p))
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, doc)
            text = para.text.strip()
            if not text:
                continue
            style = (para.style.name if para.style is not None else "") or ""
            if style == "Title" or style.startswith("Heading"):
                level = int(style.split()[-1]) if style.split()[-1].isdigit() else 1
                yield {"type": "heading", "text": text, "level": max(1, min(level, 3))}
            else:
                yield {"type": "paragraph", "text": text}
        elif tag == "tbl":
            rows = [[cell.text.strip() for cell in row.cells] for row in Table(child, doc).rows][:MAX_ROWS]
            if rows:
                yield {"type": "table", "rows": _square(rows)}


def _csv(p: Path, delimiter: str) -> Iterator[dict]:
    with p.open(newline="", encoding="utf-8", errors="replace") as f:
        rows = []
        for i, row in enumerate(csv.reader(f, delimiter=delimiter)):
            if i >= MAX_ROWS:
                break
            rows.append(row)
    if rows:
        yield {"type": "table", "rows": _square(rows)}


def _chapters(texts: Iterable[str]) -> Iterator[dict]:
    for n, text in enumerate(texts, 1):
        yield {"type": "break", "label": f"Chapter {n}"}
        for para in text.split("\n\n"):
            if para.strip():
                yield {"type": "paragraph", "text": " ".join(para.split())}
