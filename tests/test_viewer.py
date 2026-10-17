# ruff: noqa: F811  (fixtures imported from other test modules are parameters here)
"""Reading files in the app: kinds, PDF pages and matches, images, text in pieces, documents as
blocks, media streaming with seeking, and what may not be read."""

import pymupdf
import pytest
from test_ai_passes import clip, needs_ffmpeg  # noqa: F401  (fixtures)
from test_documents import office_files  # noqa: F401  (fixture)


def view(client, route: str = "", **params):
    return client.get(f"/api/view{route}", params=params)


@pytest.fixture
def report(env):
    """A three-page PDF with "harbour" on page 2 only."""
    path = env.documents / "harbour-report.pdf"
    doc = pymupdf.open()
    for text in ("Introduction to the plan", "The harbour will open in May", "Costs and next steps"):
        doc.new_page().insert_text((72, 72), text)
    doc.save(path)
    return path


def test_what_kind_of_file(local, env, report, office_files):
    def kind(path):
        return view(local, path=str(path)).json()["kind"]

    pdf_info = view(local, path=str(report)).json()
    assert pdf_info["kind"] == "pdf" and pdf_info["pages"] == 3 and len(pdf_info["shapes"]) == 3
    assert pdf_info["shapes"][0] == pytest.approx(842 / 595, abs=0.01)  # A4 portrait
    assert kind(env.files["image"]) == "image"
    assert kind(env.files["notes"]) == "text"
    assert kind(env.files["recipe"]) == "markdown"
    assert kind(env.files["docx"]) == "document"
    assert kind(office_files / "budget-2025.xlsx") == "table"
    assert kind(office_files / "roadmap.pptx") == "slides"
    (env.documents / "tool.py").write_text("print('hi')\n")
    assert (
        view(local, path=str(env.documents / "tool.py")).json() | {"kind": "code", "language": "py"}
        == view(local, path=str(env.documents / "tool.py")).json()
    )


def test_pdf_pages_and_where_the_words_are(local, report):
    one = view(local, "/page", path=str(report), page=0, w=600)
    two = view(local, "/page", path=str(report), page=1, w=600)
    assert one.status_code == two.status_code == 200 and one.headers["content-type"] == "image/png"
    assert one.content != two.content
    assert view(local, "/page", path=str(report), page=1, w=600).content == two.content  # cached
    assert view(local, "/page", path=str(report), page=7).status_code == 404

    [match] = view(local, "/find", path=str(report), q="harbour").json()
    assert match["page"] == 1 and all(0 <= v <= 1 for v in match["rects"][0])
    # a search hit's snippet: the phrase isn't on the page as a whole, its words are
    assert [m["page"] for m in view(local, "/find", path=str(report), q="harbour plans unknownword").json()] == [1]
    assert "open in May" in view(local, "/page-text", path=str(report), page=1).json()["text"]


def test_images_full_size_but_never_blown_up(local, env):
    r = view(local, "/image", path=str(env.files["image"]), w=4000)
    assert r.status_code == 200
    from io import BytesIO

    from PIL import Image

    assert Image.open(BytesIO(r.content)).size[0] == 160  # the sample is 160 px wide: not upscaled


def test_text_in_pieces(local, env):
    big = env.documents / "server.log"
    lines = [f"line {i} ✓ ok" for i in range(40000)]
    big.write_text("\n".join(lines))
    first = view(local, "/text", path=str(big), limit=64 * 1024).json()
    assert first["offset"] == 0 and not first["done"] and first["size"] == big.stat().st_size
    text, at = first["text"], first["next"]
    while True:
        piece = view(local, "/text", path=str(big), offset=at, limit=64 * 1024).json()
        text += piece["text"]
        at = piece["next"]
        if piece["done"]:
            break
    assert text == big.read_text()  # no character cut in two, nothing lost

    binary = env.documents / "data.txt"
    binary.write_bytes(b"\x00\x01\x02 not text")
    r = view(local, "/text", path=str(binary))
    assert r.status_code == 400 and "isn't text" in r.json()["error"]["message"]


def test_documents_as_blocks(local, env, office_files):
    sheet = view(local, "/blocks", path=str(office_files / "budget-2025.xlsx")).json()["blocks"]
    assert sheet[0] == {"type": "break", "label": "Budget"}
    assert sheet[1] == {"type": "table", "rows": [["Item", "Cost"], ["Travel to Lisbon", "1200"]]}
    assert {"type": "break", "label": "Notes"} in sheet

    slides = view(local, "/blocks", path=str(office_files / "roadmap.pptx")).json()["blocks"]
    assert slides[0] == {"type": "break", "label": "Slide 1"}
    assert any(b.get("text") == "Quarterly roadmap" for b in slides)
    assert any(b.get("style") == "notes" and "lighthouse" in b["text"] for b in slides)

    letter = view(local, "/blocks", path=str(env.files["docx"])).json()["blocks"]
    assert letter == [{"type": "paragraph", "text": "Dear Alex, your library card renewal is due next month."}]

    book = view(local, "/blocks", path=str(office_files / "quiet-harbour.epub")).json()["blocks"]
    assert [b["label"] for b in book if b["type"] == "break"] == ["Chapter 1", "Chapter 2"]

    csv = env.documents / "trips.csv"
    csv.write_text("city,days\nLisbon,4\nPorto,2\n")
    assert view(local, "/blocks", path=str(csv)).json()["blocks"] == [
        {"type": "table", "rows": [["city", "days"], ["Lisbon", "4"], ["Porto", "2"]]}
    ]


def test_a_word_document_keeps_headings_and_tables_in_order(local, env):
    from docx import Document

    d = Document()
    d.add_heading("Trip plan", level=1)
    d.add_paragraph("Three days in Lisbon.")
    t = d.add_table(rows=2, cols=2)
    for (r, c), value in {(0, 0): "Day", (0, 1): "Place", (1, 0): "1", (1, 1): "Alfama"}.items():
        t.cell(r, c).text = value
    d.add_paragraph("Book the tram tickets.")
    path = env.documents / "trip.docx"
    d.save(path)
    assert view(local, "/blocks", path=str(path)).json()["blocks"] == [
        {"type": "heading", "text": "Trip plan", "level": 1},
        {"type": "paragraph", "text": "Three days in Lisbon."},
        {"type": "table", "rows": [["Day", "Place"], ["1", "Alfama"]]},
        {"type": "paragraph", "text": "Book the tram tickets."},
    ]


@needs_ffmpeg
def test_video_streams_with_seeking(local, clip):
    whole = view(local, "/stream", path=str(clip))
    assert whole.status_code == 200 and whole.content == clip.read_bytes()
    part = local.get("/api/view/stream", params={"path": str(clip)}, headers={"Range": "bytes=100-199"})
    assert part.status_code == 206 and part.content == clip.read_bytes()[100:200]
    bad = local.get("/api/view/stream", params={"path": str(clip)}, headers={"Range": "bytes=999999999-"})
    assert bad.status_code == 416
    info = view(local, path=str(clip)).json()
    assert info["kind"] == "video" and info["duration"] == pytest.approx(2, abs=0.3)


def test_what_may_not_be_read(local, remote, env, tmp_path, report):
    outside = tmp_path / "secret.txt"
    outside.write_text("not for the app")
    assert view(local, "/text", path=str(outside)).status_code == 403
    assert view(local, "/text", path=str(env.documents / "missing.txt")).status_code == 404
    assert view(local, path=str(env.documents)).status_code == 400  # a folder
    assert view(local, "/stream", path=str(env.files["notes"])).status_code == 400  # only media streams
    assert view(local, "/page", path=str(env.files["notes"])).status_code == 400  # pages are for PDFs

    local.post("/api/index/exclude", json={"path": str(report)})
    r = view(local, path=str(report))
    assert r.status_code == 403 and "kept out" in r.json()["error"]["message"]

    assert view(remote, "/text", path=str(env.files["notes"])).status_code == 401  # a phone that isn't paired


def test_a_paired_phone_can_read(local, remote, env):
    code = local.post("/api/pair/start").json()["code"]
    token = remote.post("/api/pair", json={"code": code, "name": "Alex's phone"}).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    r = remote.get("/api/view/text", params={"path": str(env.files["notes"])}, headers=auth)
    assert r.status_code == 200 and "budget review" in r.json()["text"]
