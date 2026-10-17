# In-app file viewer: design and checklist

Read files inside the app, on the desktop and the phone, instead of only opening them with the
laptop's default app. View only: editing stays with the default app ("Open in default app"), so
files still change only through approval and undo.

## Design

The server prepares, the app shows: no PDF or Office libraries in Flutter, and a phone sees
exactly what the laptop sees. Every route is behind the usual auth (the laptop, or a paired phone's
token) and only serves files inside the indexed folders; files kept out of the index (Settings →
Sync) are refused too.

| Kind | Server | App |
|---|---|---|
| PDF | pages rendered as images (pymupdf, cached), matches as page + rectangles, page text | pages in a list, zoom, opens at the matched page with highlights, find |
| Image | full size scaled to the screen (cached) | zoom and pan, previous/next through the results |
| Text, Markdown, code | the text in pieces (~256 KB), binary refused | loads as you scroll; code with line numbers; Markdown formatted; matches highlighted; find |
| Word, Excel, PowerPoint, OpenDocument, EPUB, CSV | blocks: headings, paragraphs, tables, slide/sheet/chapter breaks, from the indexing readers | a readable document with real tables |
| Video, audio | the file streamed with HTTP Range (seeking) | played in the app at the found moment (gated on the media_kit spike) |

Routes: `GET /api/view` (what kind, pages, size, duration), `/api/view/page`, `/api/view/image`,
`/api/view/find`, `/api/view/page-text`, `/api/view/text`, `/api/view/blocks`, `/api/view/stream`.

A paired phone could already see thumbnails and short excerpts of files in the indexed folders;
with the viewer it can read them whole. The pairing dialog says so.

## Checklist

### 0. Set-up
- [x] Branch `viewer`; this file

### 1. Server
- [x] `lumen/viewer/kinds.py`: kind, pages, language, duration
- [x] `thumbnails.render(page=…)`, a reading-size clamp; `/api/view/page`, `/api/view/image`
- [x] `/api/view/find`, `/api/view/page-text` (pymupdf)
- [x] `/api/view/text` in pieces; binary refused
- [x] Blocks for docx, xlsx, pptx, ODF, EPUB, CSV/TSV; `/api/view/blocks` with a size cap
- [x] `/api/view/stream` with Range (206, 416)
- [x] Excluded files and paths outside the folders refused; a phone with a token allowed
- [x] Tests through the HTTP API (made-up sample files)

### 2. App: viewers
- [x] `core/api/viewer_api.dart` and models; `ViewerScreen` (top bar, back, previous/next)
- [x] `PdfView` (lazy pages, zoom, opens at the match, highlights, find)
- [x] `ImageView` (zoom, pan, double-tap, keys/swipe)
- [x] `TextView` (pieces as you scroll, line numbers, Markdown, highlights, find)
- [x] `DocumentView` (headings, paragraphs, tables, breaks)
- [x] Entry points: result cards, FileDetails, video cards, the phone's result sheet; the pairing note
- [x] Tests and screenshots (desktop and phone)

### 3. Video and audio (gated)
- [ ] Spike: media_kit in the Docker Linux build and the AppImage; libmpv; Android
- [ ] `MediaView` (start at the moment, transcript with tap to seek, speed), or keep "Play on the laptop"

### 4. Finish
- [ ] README; full checks; try it by hand; commit on the branch; merge and push (v0.5.0) when asked
