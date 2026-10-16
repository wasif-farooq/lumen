"""Passage-level search inside documents, so questions about facts ("where did I work in 2014?")
are answered from the right part of the right file instead of the first page of one file."""

import re

CHUNK = 700    # characters per passage
OVERLAP = 120  # repeated between neighbours so a fact split across a boundary is still found whole

# A date is a year, optionally preceded by month and/or day: 2014, 05/2014, 01/08/2012, 1.8.2012
_DATE = r"(?:\d{1,2}[/.-]){0,2}((?:19|20)\d{2})"
_RANGE = re.compile(
    _DATE + r"\s*(?:-|–|—|to|until|till)\s*(?:" + _DATE + r"|(current|present|now|today|date))",
    re.I,
)


def chunk_text(text: str) -> list[str]:
    """Split on blank lines / line breaks where possible, into ~CHUNK-sized overlapping passages."""
    text = re.sub(r"[ \t ]+", " ", text).strip()
    if not text:
        return []
    out, start, n = [], 0, len(text)
    while start < n:
        end = min(n, start + CHUNK)
        if end < n:
            # end at a paragraph or line break near the limit, not mid-sentence
            cut = max(text.rfind("\n\n", start + CHUNK // 2, end), text.rfind("\n", start + CHUNK // 2, end))
            if cut > start:
                end = cut
        out.append(text[start:end].strip())
        if end >= n:
            break
        start = max(end - OVERLAP, start + 1)
    return [c for c in out if c]


def years_covered(text: str, this_year: int = 2026) -> str:
    """Years inside date ranges ("09/2012 - 05/2015" -> 2012 2013 2014 2015) so a question about a
    year finds the passage even when that year is never written out."""
    years: set[int] = set()
    for m in _RANGE.finditer(text):
        a = int(m.group(1))
        b = this_year if m.group(3) else int(m.group(2))
        if a <= b and b - a <= 60:
            years.update(range(a, b + 1))
    return " ".join(str(y) for y in sorted(years))


def stem(t: str) -> str:
    """Very small English stemmer for search terms: worked/working/works -> work."""
    for suf in ("ings", "ing", "ied", "ies", "ed", "es", "s"):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)] + ("y" if suf in ("ied", "ies") else "")
    return t


def question_terms(question: str) -> list[str]:
    from .index import STOPWORDS, query_terms

    terms = []
    for t in query_terms(question):
        if t in STOPWORDS or (len(t) < 3 and not t.isdigit()):
            continue
        terms.append(stem(t))
    return list(dict.fromkeys(terms))


# ---------- index ----------

def index_file(conn, file_id: int, text: str):
    drop_file(conn, file_id)
    chunks = chunk_text(text)
    for i, chunk in enumerate(chunks):
        pid = conn.execute(
            "INSERT INTO passages (file_id, idx, total, text) VALUES (?,?,?,?)", (file_id, i, len(chunks), chunk)
        ).lastrowid
        # hidden extra words only in the search index: years covered by date ranges
        conn.execute("INSERT INTO passages_fts (rowid, text, extra) VALUES (?,?,?)", (pid, chunk, years_covered(chunk)))


def drop_file(conn, file_id: int):
    conn.execute("DELETE FROM passages_fts WHERE rowid IN (SELECT id FROM passages WHERE file_id=?)", (file_id,))
    conn.execute("DELETE FROM passages WHERE file_id=?", (file_id,))


def backfill(conn) -> int:
    """Passages for every file whose indexed content has none yet: documents indexed before passages
    existed, and images/scans/videos whose description or transcript was just added."""
    rows = conn.execute(
        "SELECT f.id, t.content FROM files f JOIN files_fts t ON t.rowid = f.id "
        "WHERE t.content != '' AND NOT EXISTS (SELECT 1 FROM passages p WHERE p.file_id = f.id)"
    ).fetchall()
    for r in rows:
        index_file(conn, r["id"], r["content"] or "")
    return len(rows)


# ---------- search ----------

def search(conn, question: str, limit: int = 6, folder: str = "", ext: str = "", relevance_sql: str = "1.0") -> list[dict]:
    """Best passages across all documents. bm25 rewards passages matching more (and rarer) terms."""
    terms = question_terms(question)
    if not terms:
        return []
    q = lambda t: f'"{t}"' if t.isdigit() else f'"{t}"*'
    numbers = [t for t in terms if t.isdigit()]
    words = [t for t in terms if not t.isdigit()]
    # Strictest first. Numbers (years, amounts, IDs) are precise, so passages containing them come
    # before passages that only share common words like "work".
    steps = [" AND ".join(q(t) for t in terms)]
    if numbers:
        num = " AND ".join(q(t) for t in numbers)
        if words:
            steps.append(f"{num} AND ({' OR '.join(q(t) for t in words)})")
        steps.append(num)
    steps.append(" OR ".join(q(t) for t in terms))
    where, params = [], []
    if folder:
        where.append("f.path LIKE ?")
        params.append(f"%{folder}%")
    exts = [e.strip().lower().lstrip(".") for e in re.split(r"[,\s]+", ext) if e.strip()]
    if exts:
        where.append(f"f.ext IN ({','.join('?' * len(exts))})")
        params += exts
    sql = (
        "SELECT p.id, p.text, p.idx, p.total, f.path, f.name, f.ext, f.size, f.mtime, f.duration, "
        f"bm25(passages_fts, 1.0, 1.0) * {relevance_sql} AS score "
        "FROM passages_fts JOIN passages p ON p.id = passages_fts.rowid JOIN files f ON f.id = p.file_id "
        "WHERE passages_fts MATCH ?" + "".join(" AND " + w for w in where) + " ORDER BY score LIMIT ?"
    )
    # at most 2 passages per file, so one long document doesn't crowd out the others
    out, per_file, seen = [], {}, set()
    for match in steps:
        for r in conn.execute(sql, (match, *params, limit * 4)).fetchall():
            key = (r["path"], " ".join(r["text"].split())[:80])
            if r["id"] in seen or key in seen or per_file.get(r["path"], 0) >= 2:
                continue
            seen.update((r["id"], key))
            per_file[r["path"]] = per_file.get(r["path"], 0) + 1
            out.append(dict(r))
            if len(out) >= limit:
                return out
    return out


def best_parts(text: str, question: str, budget: int) -> tuple[list[tuple[int, str]], int]:
    """For reading one long file: the passages most relevant to the question, in document order,
    always including the opening passage (title, name, summary). Returns ([(index, passage)], total)."""
    chunks = chunk_text(text)
    terms = question_terms(question)

    def score(c: str) -> float:
        low = (c + " " + years_covered(c)).lower()
        return sum(low.count(t) * (3 if t.isdigit() else 1) for t in terms)

    ranked = sorted(range(len(chunks)), key=lambda i: -score(chunks[i]))
    best_parts.matched = any(score(c) > 0 for c in chunks)
    picked, used = {0}, len(chunks[0]) if chunks else 0
    for i in ranked:
        if score(chunks[i]) == 0 or used + len(chunks[i]) > budget:
            continue
        picked.add(i)
        used += len(chunks[i])
    return [(i, chunks[i]) for i in sorted(picked)], len(chunks)
