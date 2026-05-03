"""Simple data cleaning pipeline for Douban scraped items.

Provides functions to normalize common fields (rating, comment_count, imdb, runtime)
before saving to file or database.
"""

from __future__ import annotations

import re

from .parser import DoubanItem


def clean_items(items: list[DoubanItem]) -> list[DoubanItem]:
    """Apply standard cleaning transforms to a list of DoubanItem (in-place).

    Cleans the following fields:
      - **rating**: keeps only valid float string (e.g. ``"9.7"``)
      - **comment_count**: keeps only digits (e.g. ``"3282402"``)
      - **imdb**: extracts ``ttXXXXXX`` ID, discarding extra text
      - **runtime**: converts to ``int`` (minutes), discarding unit/notes
    """
    for item in items:
        _clean_rating(item)
        _clean_comment_count(item)
        _clean_imdb(item)
        _clean_runtime(item)
    return items


# ---------------------------------------------------------------------------
# Internal cleaners
# ---------------------------------------------------------------------------

def _clean_rating(item: DoubanItem) -> None:
    rating = item.rating.strip()
    if not rating:
        return
    match = re.search(r"\d+(?:\.\d+)?", rating)
    item.rating = match.group(0) if match else ""


def _clean_comment_count(item: DoubanItem) -> None:
    count = item.comment_count.strip()
    if not count:
        return
    # Remove commas first, then extract digits
    match = re.search(r"\d+", count.replace(",", ""))
    item.comment_count = match.group(0) if match else ""


def _clean_imdb(item: DoubanItem) -> None:
    imdb = item.imdb.strip()
    if not imdb:
        return
    match = re.search(r"(tt\d+)", imdb)
    item.imdb = match.group(1) if match else ""


def _clean_runtime(item: DoubanItem) -> None:
    runtime = item.runtime
    if runtime is None:
        return
    if isinstance(runtime, int):
        return  # already clean
    # String value like "142分钟(国际版)" or "142"
    runtime = runtime.strip()
    if not runtime:
        item.runtime = None
        return
    match = re.search(r"(\d+)", runtime)
    item.runtime = int(match.group(1)) if match else None
