"""Parsers for Douban list/search and movie detail pages."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Iterable
from urllib.parse import urljoin

try:
    from bs4 import BeautifulSoup, NavigableString, Tag
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
    "IMDb链接",
)


@dataclass
class DoubanItem:
    rank: str
    title: str
    url: str
    title_cn: str = ""
    title_en: str = ""
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
    runtime: str | None = None
    imdb: str = ""
    short_comments: str = ""
    detail_error: str = ""

    def to_dict(self) -> dict[str, str | None]:
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
    return bool(soup.select_one("#info") or soup.select_one("script[type='application/ld+json']"))


def enrich_movie_detail(item: DoubanItem, html: str) -> DoubanItem:
    """Fill a list item with fields parsed from a Douban movie detail page."""

    soup = BeautifulSoup(html, "lxml")
    info = soup.select_one("#info")
    if not info:
        if _enrich_from_json_ld(item, soup) or _enrich_from_mobile_text(item, soup):
            item.detail_error = ""
            return item
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
    item.imdb = _info_label(soup, "IMDb链接") or _info_label(soup, "IMDb")
    item.detail_error = ""
    return item


def parse_movie_comments(html: str, limit: int) -> list[str]:
    """Parse Douban short comments from detail or comments pages."""

    if limit <= 0:
        return []

    soup = BeautifulSoup(html, "lxml")
    comments: list[str] = []
    for node in soup.select(".comment-item, .comment"):
        text = _first_text(node, ".short, .comment-content")
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
        title_cn = title_nodes[0] if title_nodes else title
        title_en = " ".join(node.strip(" /") for node in title_nodes[1:] if node.strip(" /"))
        link = _first_attr(card, ".hd a", "href")
        rank = _first_text(card, ".pic em")
        rating = _first_text(card, ".rating_num")
        comments = _top250_comment_count(card)
        summary = _first_text(card, ".inq") or _first_text(card, ".quote .inq")
        image = _first_attr(card, "img", "src")
        item_info = _parse_top250_card_info(card)
        if title and link:
            yield DoubanItem(
                rank=rank,
                title=title,
                url=urljoin(source_url, link),
                title_cn=title_cn,
                title_en=title_en,
                rating=rating,
                comment_count=comments,
                summary=summary,
                image_url=image,
                source_page=source_url,
                director=item_info.get("director", ""),
                actors=item_info.get("actors", ""),
                genres=item_info.get("genres", ""),
                country=item_info.get("country", ""),
                release_date=item_info.get("release_date", ""),
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
                rank="",
                title=title,
                url=urljoin(source_url, link),
                rating=_first_text(card, ".rating_nums, .rating_num, .allstar50, .allstar45"),
                comment_count=_numbers_only(_first_text(card, ".pl, .comment, .star span")),
                summary=_first_text(card, ".content, .desc, p"),
                image_url=_first_attr(card, "img", "src") or _first_attr(card, "img", "data-src"),
                source_page=source_url,
            )


def _parse_top250_card_info(card: Tag) -> dict[str, str]:
    info_node = card.select_one(".bd p")
    if not info_node:
        return {}

    html = str(info_node).replace("<br/>", "\n").replace("<br>", "\n")
    text = BeautifulSoup(html, "lxml").get_text("\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return {}

    result: dict[str, str] = {}
    people_line = lines[0]
    meta_line = lines[1] if len(lines) > 1 else ""

    director_match = re.search(r"导演:\s*(.+?)(?=\s+主演:|$)", people_line)
    if director_match:
        result["director"] = _normalize_space(director_match.group(1))

    actors_match = re.search(r"主演:\s*(.+)$", people_line)
    if actors_match:
        result["actors"] = _normalize_space(actors_match.group(1))

    meta_parts = [part.strip() for part in meta_line.split("/") if part.strip()]
    if meta_parts:
        result["release_date"] = meta_parts[0]
    if len(meta_parts) >= 2:
        result["country"] = meta_parts[1]
    if len(meta_parts) >= 3:
        result["genres"] = " / ".join(meta_parts[2:])
    return result


def _enrich_from_json_ld(item: DoubanItem, soup: BeautifulSoup) -> bool:
    for node in soup.select("script[type='application/ld+json']"):
        payload = node.string or node.get_text("", strip=True)
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if _json_ld_type(candidate) not in {"Movie", "TVSeries", "CreativeWork"}:
                continue
            _apply_json_ld(item, candidate)
            return True
    return False


def _json_ld_type(data: dict[str, object]) -> str:
    value = data.get("@type", "")
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value)


def _apply_json_ld(item: DoubanItem, data: dict[str, object]) -> None:
    item.title = _json_text(data.get("name")) or item.title
    item.summary = _json_text(data.get("description")) or item.summary
    item.image_url = _json_text(data.get("image")) or item.image_url
    item.director = _json_people(data.get("director")) or item.director
    item.actors = _json_people(data.get("actor")) or item.actors
    item.screenwriter = _json_people(data.get("author")) or item.screenwriter
    item.genres = _json_join(data.get("genre")) or item.genres
    item.release_date = _json_text(data.get("datePublished")) or item.release_date
    item.runtime = _json_text(data.get("duration")) or item.runtime

    rating = data.get("aggregateRating")
    if isinstance(rating, dict):
        item.rating = _json_text(rating.get("ratingValue")) or item.rating
        item.comment_count = _json_text(rating.get("ratingCount")) or item.comment_count


def _enrich_from_mobile_text(item: DoubanItem, soup: BeautifulSoup) -> bool:
    title = _first_text(soup, "h1, .sub-title, title")
    if title:
        item.title = title.replace("(豆瓣)", "").strip()

    summary = _first_text(soup, ".subject-intro, .intro, [data-clamp]")
    if summary:
        item.summary = _normalize_space(summary)

    text = soup.get_text("\n", strip=True)
    field_map = {
        "导演": "director",
        "编剧": "screenwriter",
        "主演": "actors",
        "类型": "genres",
        "制片国家/地区": "country",
        "语言": "language",
        "上映日期": "release_date",
        "片长": "runtime",
        "IMDb": "imdb",
    }
    matched = False
    for label, attr in field_map.items():
        value = _text_label(text, label)
        if value:
            setattr(item, attr, value)
            matched = True
    return matched


def _text_label(text: str, label: str) -> str:
    labels = "|".join(re.escape(item) for item in INFO_LABELS)
    match = re.search(rf"{re.escape(label)}\s*:?\s*(.+?)(?=\n(?:{labels})\s*:|\Z)", text, re.S)
    if not match:
        return ""
    return _normalize_space(match.group(1))


def _json_people(value: object) -> str:
    if isinstance(value, dict):
        return _json_text(value.get("name"))
    if isinstance(value, list):
        names = [_json_people(item) for item in value]
        return " / ".join(name for name in names if name)
    return _json_text(value)


def _json_join(value: object) -> str:
    if isinstance(value, list):
        return " / ".join(_json_text(item) for item in value if _json_text(item))
    return _json_text(value)


def _json_text(value: object) -> str:
    if value is None:
        return ""
    return _normalize_space(str(value))


def _top250_comment_count(card: Tag) -> str:
    text = _first_text(card, ".star span:last-child")
    if text:
        return _numbers_only(text)
    star_text = _first_text(card, ".star")
    return _numbers_only(star_text)


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

    label_node = info.find("span", class_="pl", string=re.compile(rf"^{re.escape(label)}\s*:"))
    if label_node:
        return _value_after_label(label_node)

    text = info.get_text(" ", strip=True)
    next_labels = "|".join(re.escape(item) for item in INFO_LABELS)
    pattern = rf"{re.escape(label)}\s*:?\s*(.+?)(?=(?:{next_labels})\s*:|$)"
    match = re.search(pattern, text, flags=re.S)
    if not match:
        return ""
    return _normalize_space(match.group(1))


def _value_after_label(label_node: Tag) -> str:
    values: list[str] = []
    for sibling in label_node.next_siblings:
        if isinstance(sibling, Tag) and "pl" in sibling.get("class", []):
            break
        if isinstance(sibling, Tag):
            text = sibling.get_text(" ", strip=True)
        elif isinstance(sibling, NavigableString):
            text = str(sibling)
        else:
            text = ""
        text = _normalize_space(text)
        if text:
            values.append(text)
    return _normalize_space(" ".join(values).lstrip(":： "))


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
