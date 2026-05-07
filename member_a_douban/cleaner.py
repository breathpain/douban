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
      - **rank**: converts to ``int`` (e.g. ``1``)
      - **rating**: converts to ``float`` (e.g. ``9.7``)
      - **comment_count**: converts to ``int`` (e.g. ``3282402``)
      - **imdb**: extracts ``ttXXXXXX`` ID, discarding extra text
      - **runtime**: keeps as ``int`` (minutes)
    """
    for item in items:
        _clean_rank(item)
        _clean_rating(item)
        _clean_comment_count(item)
        _clean_imdb(item)
        _clean_runtime(item)
    return items


# ---------------------------------------------------------------------------
# Internal cleaners
# ---------------------------------------------------------------------------

def _clean_rank(item: DoubanItem) -> None:
    rank = item.rank
    if rank is None:
        return
    if isinstance(rank, int):
        return  # already clean
    rank = rank.strip()
    if not rank:
        item.rank = None
        return
    match = re.search(r"\d+", rank)
    item.rank = int(match.group(0)) if match else None


def _clean_rating(item: DoubanItem) -> None:
    rating = item.rating
    if rating is None:
        return
    if isinstance(rating, (int, float)):
        item.rating = float(rating)
        return
    rating = rating.strip()
    if not rating:
        item.rating = None
        return
    match = re.search(r"\d+(?:\.\d+)?", rating)
    item.rating = float(match.group(0)) if match else None


def _clean_comment_count(item: DoubanItem) -> None:
    count = item.comment_count
    if count is None:
        return
    if isinstance(count, int):
        return  # already clean
    count = count.strip()
    if not count:
        item.comment_count = None
        return
    # Remove commas first, then extract digits
    match = re.search(r"\d+", count.replace(",", ""))
    item.comment_count = int(match.group(0)) if match else None


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
