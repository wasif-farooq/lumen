"""`lumen search` and `lumen stats`: the index without the AI."""

import argparse

from ..search import text as text_search
from ..storage import catalog
from .console import console


def stats(_: argparse.Namespace) -> None:
    console.print(catalog.stats())


def search(a: argparse.Namespace) -> None:
    hits = text_search.search(" ".join(a.words), a.ext, a.after, a.before, a.folder, a.limit)
    for i, h in enumerate(hits, 1):
        console.print(h.line(i), highlight=False, markup=False)
    if not hits:
        console.print("No results.")
