"""Parsers for Douban list/search pages."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Iterable
from urllib.parse import urljoin

try:
    from bs4 import BeautifulSoup, Tag
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise ModuleNotFoundError(
        "beautifulsoup4 and lxml are required. Install dependencies with: pip install -r requirements.txt"
    ) from exc


@dataclass
class DoubanItem:
    title: str
    url: str
    rating: str = ""
    comment_count: str = ""
    summary: str = ""
    image_url: str = ""
    source_page: str = ""
    image_file: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def parse_douban_items(html: str, source_url: str) -> list[DoubanItem]:
    """Parse common Douban list pages, especially movie Top250 pages."""

    soup = BeautifulSoup(html, "lxml")
    items = list(_parse_movie_top250(soup, source_url))
    if items:
        return items
    return list(_parse_generic_cards(soup, source_url))


def _parse_movie_top250(soup: BeautifulSoup, source_url: str) -> Iterable[DoubanItem]:
    for card in soup.select(".grid_view li"):
        title_nodes = [node.get_text(strip=True) for node in card.select(".hd .title")]
        title = " ".join(dict.fromkeys(title_nodes)).strip()
        link = _first_attr(card, ".hd a", "href")
        rating = _first_text(card, ".rating_num")
        comments = _first_text(card, ".star span:last-child")
        summary = _first_text(card, ".inq")
        image = _first_attr(card, "img", "src")
        if title and link:
            yield DoubanItem(
                title=title,
                url=urljoin(source_url, link),
                rating=rating,
                comment_count=_numbers_only(comments),
                summary=summary,
                image_url=image,
                source_page=source_url,
            )


def _parse_generic_cards(soup: BeautifulSoup, source_url: str) -> Iterable[DoubanItem]:
    selectors = (
        ".result",
        ".item-root",
        ".item",
        "article",
        ".subject-item",
    )
    seen: set[str] = set()
    for selector in selectors:
        for card in soup.select(selector):
            title, link = _title_and_link(card)
            if not title or not link or link in seen:
                continue
            seen.add(link)
            yield DoubanItem(
                title=title,
                url=urljoin(source_url, link),
                rating=_first_text(card, ".rating_nums, .rating_num, .allstar50, .allstar45"),
                comment_count=_numbers_only(_first_text(card, ".pl, .comment, .star span")),
                summary=_first_text(card, ".content, .desc, p"),
                image_url=_first_attr(card, "img", "src") or _first_attr(card, "img", "data-src"),
                source_page=source_url,
            )


def _title_and_link(card: Tag) -> tuple[str, str]:
    link_node = card.select_one("a[href]")
    if not link_node:
        return "", ""
    title = link_node.get("title") or link_node.get_text(" ", strip=True)
    return str(title).strip(), str(link_node.get("href", "")).strip()


def _first_text(card: Tag | BeautifulSoup, selector: str) -> str:
    node = card.select_one(selector)
    return node.get_text(" ", strip=True) if node else ""


def _first_attr(card: Tag | BeautifulSoup, selector: str, attr: str) -> str:
    node = card.select_one(selector)
    if not node:
        return ""
    value = node.get(attr)
    return str(value).strip() if value else ""


def _numbers_only(text: str) -> str:
    match = re.search(r"[\d,]+", text)
    return match.group(0).replace(",", "") if match else text
