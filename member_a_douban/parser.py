"""Parsers for Douban list/search and movie detail pages."""

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


INFO_LABELS = (
    "导演",
    "编剧",
    "主演",
    "类型",
    "官方网站",
    "制片国家/地区",
    "语言",
    "上映日期",
    "片长",
    "又名",
    "IMDb",
)


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
    director: str = ""
    screenwriter: str = ""
    actors: str = ""
    genres: str = ""
    country: str = ""
    language: str = ""
    release_date: str = ""
    runtime: str = ""
    imdb: str = ""
    short_comments: str = ""
    detail_error: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def parse_douban_items(html: str, source_url: str) -> list[DoubanItem]:
    """Parse common Douban list pages, especially movie Top250 pages."""

    soup = BeautifulSoup(html, "lxml")
    items = list(_parse_movie_top250(soup, source_url))
    if items:
        return items
    return list(_parse_generic_cards(soup, source_url))


def has_movie_detail_info(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    return bool(soup.select_one("#info"))


def enrich_movie_detail(item: DoubanItem, html: str) -> DoubanItem:
    """Fill a list item with fields parsed from a Douban movie detail page."""

    soup = BeautifulSoup(html, "lxml")
    info = soup.select_one("#info")
    if not info:
        page_title = _first_text(soup, "title")
        item.detail_error = f"detail page missing #info, page_title={page_title[:80]}"
        return item

    title = _first_text(soup, "h1 span[property='v:itemreviewed']")
    if title:
        item.title = title

    rating = _first_text(soup, "strong.rating_num")
    if rating:
        item.rating = rating

    votes = _first_text(soup, "span[property='v:votes']")
    if votes:
        item.comment_count = votes

    # 优先取展开后的完整简介 (span.all)，其次取截断版 (span[property='v:summary'])
    summary = _first_text(soup, "#link-report-intra .all")
    if not summary:
        summary = _first_text(soup, "#link-report-intra span[property='v:summary']")
    if summary:
        item.summary = _normalize_space(summary)

    image = _first_attr(soup, "#mainpic img", "src")
    if image:
        item.image_url = image

    item.director = _join_texts(soup, "[rel='v:directedBy']") or _info_label(soup, "导演")
    item.screenwriter = _info_label(soup, "编剧")
    item.actors = _join_texts(soup, "[rel='v:starring']") or _info_label(soup, "主演")
    item.genres = _join_texts(soup, "[property='v:genre']") or _info_label(soup, "类型")
    item.country = _info_label(soup, "制片国家/地区")
    item.language = _info_label(soup, "语言")
    item.release_date = _join_texts(soup, "[property='v:initialReleaseDate']") or _info_label(
        soup, "上映日期"
    )
    item.runtime = _first_text(soup, "[property='v:runtime']") or _info_label(soup, "片长")
    item.imdb = _info_label(soup, "IMDb")
    return item


def parse_movie_comments(html: str, limit: int) -> list[str]:
    """Parse Douban short comments from detail or comments pages."""

    if limit <= 0:
        return []

    soup = BeautifulSoup(html, "lxml")
    comments: list[str] = []
    for node in soup.select(".comment-item"):
        text = _first_text(node, ".short")
        if not text:
            continue
        author = _first_text(node, ".comment-info a")
        rating = _comment_rating(node)
        date = _first_text(node, ".comment-time")
        votes = _first_text(node, ".votes")

        parts = []
        if author:
            parts.append(f"用户：{author}")
        if rating:
            parts.append(f"评分：{rating}")
        if date:
            parts.append(f"时间：{date}")
        if votes:
            parts.append(f"有用：{votes}")
        parts.append(f"评论：{_normalize_space(text)}")
        comments.append(" | ".join(parts))
        if len(comments) >= limit:
            break
    return comments


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


def _join_texts(soup: BeautifulSoup, selector: str) -> str:
    values = [node.get_text(" ", strip=True) for node in soup.select(selector)]
    return " / ".join(value for value in values if value)


def _comment_rating(node: Tag) -> str:
    rating_node = node.select_one(".comment-info .rating")
    if not rating_node:
        return ""
    title = rating_node.get("title")
    if title:
        return str(title).strip()
    classes = " ".join(rating_node.get("class", []))
    match = re.search(r"allstar(\d+)", classes)
    if not match:
        return ""
    return f"{int(match.group(1)) // 10}星"


def _info_label(soup: BeautifulSoup, label: str) -> str:
    info = soup.select_one("#info")
    if not info:
        return ""

    text = info.get_text(" ", strip=True)
    next_labels = "|".join(re.escape(item) for item in INFO_LABELS)
    pattern = rf"{re.escape(label)}\s*:?\s*(.+?)(?=(?:{next_labels})\s*:|$)"
    match = re.search(pattern, text, flags=re.S)
    if not match:
        return ""
    return _normalize_space(match.group(1))


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
