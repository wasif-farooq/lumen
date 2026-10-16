"""Reading a search: its words, and the full-text (FTS5) queries tried from strictest to loosest."""

import re

# fmt: off
STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "for", "with", "by", "from", "is", "are",
    "was", "be", "it", "its", "this", "that", "what", "which", "who", "where", "when", "how", "does", "do",
    "did", "i", "me", "my", "you", "your", "we", "our", "he", "she", "they", "them", "someone", "says",
    "say", "said", "s",
    # request words: "find my CV" is a search for "cv"
    "find", "show", "open", "search", "look", "get", "give", "list", "please", "can", "could", "file",
    "files", "all", "any", "some", "have", "got", "about", "there", "here", "pls",
}
# fmt: on


# 3-letter words that are usually abbreviations, where a prefix match is noise
_EXACT_SHORT = {"cv", "id", "pdf", "cnic", "ntn", "pay", "car", "bill"}


def fts_term(t: str) -> str:
    """FTS5 term: prefix match for real words ("invoic" finds "invoices"), exact match for short
    ones, which would otherwise hit unrelated longer words ("cv" in "cva", "tax" stays prefix)."""
    return f'"{t}"' if len(t) <= 2 or (len(t) == 3 and not t.isalpha()) or t in _EXACT_SHORT else f'"{t}"*'


def query_terms(query: str) -> list[str]:
    """Search words, with TV episode notation unified to how files are named:
    "season 1 episode 2", "s1e2", "1x02" -> "s01e02"."""
    q = query.lower()

    def ep(m: re.Match) -> str:
        return f" s{int(m.group(1)):02d}e{int(m.group(2)):02d} "

    q = re.sub(r"\bseason\s*(\d{1,2})[\s,]*(?:episode|ep|e)\s*(\d{1,3})\b", ep, q)
    q = re.sub(r"\bs(\d{1,2})\s*e(\d{1,3})\b", ep, q)
    q = re.sub(r"\b(\d{1,2})x(\d{2,3})\b", ep, q)
    return re.findall(r"[^\W_]+", q)


def match_exprs(terms: list[str], loose: bool = True) -> list[tuple[str, bool]]:
    """FTS5 queries from strictest to loosest: exact phrase, all words, any word.
    Each comes with a flag: True when it is the partial ("any word") step.
    The looser steps skip filler words, bare numbers and very short words,
    which would otherwise match nearly everything (dates, resolutions, "it", "1")."""
    if len(terms) == 1:
        return [(fts_term(terms[0]), False)]
    content = [t for t in terms if t not in STOPWORDS] or terms
    exprs = [('"' + " ".join(terms) + '"', False), (" AND ".join(fts_term(t) for t in content), False)]
    meaningful = [t for t in content if len(t) >= 3 and not t.isdigit()]
    if loose and len(meaningful) > 1:
        exprs.append((" OR ".join(fts_term(t) for t in meaningful), True))
    return exprs
