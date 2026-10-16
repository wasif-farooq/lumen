"""Text from office documents and e-books: Excel and PowerPoint (xlsx, pptx), OpenDocument
(odt, ods, odp) and EPUB. All are zip files of XML; each is read member by member and streamed,
so a big file is never held in memory whole, and reading stops once enough text is found."""

import codecs
import re
import zipfile
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import IO, Literal
from xml.etree.ElementTree import Element, iterparse

from ..core import limits

NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkg": "http://schemas.openxmlformats.org/package/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
    "opf": "http://www.idpf.org/2007/opf",
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
}


def _tag(ns: str, name: str) -> str:
    return f"{{{NS[ns]}}}{name}"


class _Capped:
    """A zip member that stops after a set number of bytes: a "zip bomb" (a small file that
    unpacks to gigabytes) can't keep the indexer busy."""

    def __init__(self, raw: IO[bytes]) -> None:
        self.raw, self.left = raw, limits.MAX_UNPACKED_BYTES

    def read(self, n: int = -1) -> bytes:
        if self.left <= 0:
            return b""
        data = self.raw.read(self.left if n < 0 else min(n, self.left))
        self.left -= len(data)
        return data


def _parse(
    zf: zipfile.ZipFile, name: str, events: tuple[Literal["start", "end"], ...] = ("end",)
) -> Iterator[tuple[str, Element]]:
    with zf.open(name) as raw:
        yield from iterparse(_Capped(raw), events=events)


def _texts(el: Element) -> str:
    return "".join(el.itertext())


# ---------- Excel ----------


def xlsx(path: Path) -> Iterator[str]:
    """Each sheet's name, then its rows with cells separated by |."""
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            for _, el in _parse(zf, "xl/sharedStrings.xml"):
                if el.tag == _tag("main", "si"):
                    shared.append(_texts(el))
                    el.clear()
        targets = {}
        for _, el in _parse(zf, "xl/_rels/workbook.xml.rels"):
            if el.tag == _tag("pkg", "Relationship"):
                targets[el.get("Id")] = "xl/" + (el.get("Target") or "").removeprefix("/xl/")
        sheets = [
            (el.get("name") or "", targets.get(el.get(_tag("rel", "id"))))
            for _, el in _parse(zf, "xl/workbook.xml")
            if el.tag == _tag("main", "sheet")
        ]
        for name, member in sheets:
            if member not in names:
                continue
            yield f"Sheet: {name}"
            row: list[str] = []
            for _, el in _parse(zf, member):
                if el.tag == _tag("main", "c"):
                    kind, value = el.get("t"), el.find("main:v", NS)
                    if kind == "s" and value is not None and (value.text or "").isdigit():
                        row.append(shared[int(value.text or 0)] if int(value.text or 0) < len(shared) else "")
                    elif kind == "inlineStr":
                        row.append(_texts(el))
                    elif value is not None:
                        row.append(value.text or "")
                elif el.tag == _tag("main", "row"):
                    if any(c.strip() for c in row):
                        yield " | ".join(row)
                    row = []
                    el.clear()


# ---------- PowerPoint ----------


def _number(name: str) -> int:
    m = re.search(r"(\d+)\.xml$", name)
    return int(m.group(1)) if m else 0


def pptx(path: Path) -> Iterator[str]:
    """Each slide's text in slide order, then its speaker notes."""
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        slides = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=_number)
        notes = {_number(n): n for n in names if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n)}
        for slide in slides:
            yield f"Slide {_number(slide)}"
            yield from _paragraphs(zf, slide)
            if _number(slide) in notes:
                lines = [p for p in _paragraphs(zf, notes[_number(slide)]) if not p.isdigit()]  # skip slide numbers
                if lines:
                    yield "Notes: " + "\n".join(lines)


def _paragraphs(zf: zipfile.ZipFile, member: str) -> Iterator[str]:
    for _, el in _parse(zf, member):
        if el.tag == _tag("a", "p"):
            text = "".join(t.text or "" for t in el.iter(_tag("a", "t"))).strip()
            if text:
                yield text


# ---------- OpenDocument ----------


def odf(path: Path) -> Iterator[str]:
    """Text documents, spreadsheets and presentations: paragraphs and headings in order; table
    rows with cells separated by |."""
    para, cell, row = (_tag("text", "p"), _tag("text", "h")), _tag("table", "table-cell"), _tag("table", "table-row")
    cells: list[str] | None = None  # the row being read, when inside a table
    current: list[str] = []
    with zipfile.ZipFile(path) as zf:
        for event, el in _parse(zf, "content.xml", events=("start", "end")):
            if event == "start":
                if el.tag == row:
                    cells = []
                continue
            if el.tag in para:
                text = _texts(el).strip()
                if cells is None:
                    if text:
                        yield text
                    el.clear()
                elif text:
                    current.append(text)
            elif el.tag == cell and cells is not None:
                cells.append(" ".join(current))
                current = []
                el.clear()
            elif el.tag == row and cells is not None:
                if any(c.strip() for c in cells):
                    yield " | ".join(c for c in cells if c.strip())
                cells = None
                el.clear()


# ---------- EPUB ----------


class _HtmlText(HTMLParser):
    BLOCKS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "blockquote"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style", "head"):
            self.skip += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "head") and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def epub(path: Path) -> Iterator[str]:
    """The book's chapters in reading order (the spine), as plain text."""
    with zipfile.ZipFile(path) as zf:
        opf = ""
        for _, el in _parse(zf, "META-INF/container.xml"):
            if el.tag == _tag("container", "rootfile"):
                opf = el.get("full-path") or ""
                break
        if not opf:
            return
        base = PurePosixPath(opf).parent
        manifest, spine = {}, []
        for _, el in _parse(zf, opf):
            if el.tag == _tag("opf", "item"):
                manifest[el.get("id")] = el.get("href") or ""
            elif el.tag == _tag("opf", "itemref"):
                spine.append(el.get("idref"))
        names = set(zf.namelist())
        for idref in spine:
            member = str(base / manifest.get(idref, "")) if str(base) != "." else manifest.get(idref, "")
            if member not in names:
                continue
            parser, decode = _HtmlText(), codecs.getincrementaldecoder("utf-8")(errors="replace")
            with zf.open(member) as f:
                capped = _Capped(f)
                while chunk := capped.read(1 << 20):
                    parser.feed(decode.decode(chunk))
            parser.feed(decode.decode(b"", final=True))
            parser.close()
            text = re.sub(r"\n\s*\n+", "\n\n", "".join(parser.parts)).strip()
            if text:
                yield text
