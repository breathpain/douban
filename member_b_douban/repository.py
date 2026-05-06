"""Data-access layer: insert movies & comments into MySQL."""

from __future__ import annotations

import re

from .config import MySQLConfig
from .database import create_tables, get_connection, init_database


def save_movies_with_comments(cfg: MySQLConfig, items: list[dict]) -> int:
    """
    Insert movie records (and their short comments) into MySQL.

    Returns the number of movies actually inserted (excludes duplicates).
    """
    init_database(cfg)
    create_tables(cfg)

    conn = get_connection(cfg)
    inserted = 0
    try:
        with conn.cursor() as cur:
            for item in items:
                movie_id = _upsert_movie(cur, item)
                if movie_id:
                    inserted += 1
                    _save_comments(cur, movie_id, item.get("short_comments", ""))
        conn.commit()
    finally:
        conn.close()

    return inserted


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

INSERT_MOVIE_SQL = """
    INSERT INTO movies (
        `rank`, title, title_cn, title_en, url, rating,
        comment_count, summary,
        image_url, source_page, image_file,
        director, screenwriter, actors, genres,
        country, language, release_date, runtime, imdb,
        detail_error
    ) VALUES (
        %(rank)s, %(title)s, %(title_cn)s, %(title_en)s, %(url)s, %(rating)s,
        %(comment_count)s, %(summary)s,
        %(image_url)s, %(source_page)s, %(image_file)s,
        %(director)s, %(screenwriter)s, %(actors)s, %(genres)s,
        %(country)s, %(language)s, %(release_date)s, %(runtime)s, %(imdb)s,
        %(detail_error)s
    )
    ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)
"""

INSERT_COMMENT_SQL = """
    INSERT IGNORE INTO comments (movie_id, `user`, rating, comment_time, helpful, `comment`)
    VALUES (%s, %s, %s, %s, %s, %s)
"""


def _upsert_movie(cur, item: dict) -> int | None:
    """Insert or update a movie; return its id (or None on failure)."""

    # Only keep fields that match the movies table columns
    fields = {
        "rank": (item.get("rank") or "")[:10],
        "title": (item.get("title") or "")[:255],
        "title_cn": (item.get("title_cn") or "")[:255],
        "title_en": (item.get("title_en") or "")[:255],
        "url": (item.get("url") or "")[:512],
        "rating": (item.get("rating") or "")[:10],
        "comment_count": (item.get("comment_count") or "")[:20],
        "summary": item.get("summary") or "",
        "image_url": (item.get("image_url") or "")[:512],
        "source_page": (item.get("source_page") or "")[:512],
        "image_file": (item.get("image_file") or "")[:512],
        "director": (item.get("director") or "")[:255],
        "screenwriter": (item.get("screenwriter") or "")[:255],
        "actors": item.get("actors") or "",
        "genres": (item.get("genres") or "")[:255],
        "country": (item.get("country") or "")[:255],
        "language": (item.get("language") or "")[:255],
        "release_date": (item.get("release_date") or "")[:255],
        "runtime": item.get("runtime"),
        "imdb": (item.get("imdb") or "")[:50],
        "detail_error": item.get("detail_error") or "",
    }

    cur.execute(INSERT_MOVIE_SQL, fields)
    return cur.lastrowid


def _parse_comment_line(line: str) -> dict[str, str]:
    """
    Parse a single raw comment line into its component fields.

    Expected format:
        用户：xxx | 评分：xxx | 时间：xxx | 有用：xxx | 评论：xxx
    Some fields (e.g. 评分) may be missing.
    """
    fields = {
        "用户": "user",
        "评分": "rating",
        "时间": "comment_time",
        "有用": "helpful",
        "评论": "comment",
    }
    result: dict[str, str] = {
        "user": "",
        "rating": "",
        "comment_time": "",
        "helpful": "",
        "comment": "",
    }

    key_pattern = "|".join(re.escape(k) for k in fields)
    pattern = re.compile(
        rf"(?:^|\|\s*)({key_pattern})：(.+?)(?=\s*\|\s*(?:{key_pattern})：|\s*$)"
    )

    for m in pattern.finditer(line):
        cn_key = m.group(1)
        value = m.group(2).strip()
        result[fields[cn_key]] = value

    return result


def _save_comments(cur, movie_id: int, raw_comments: str) -> None:
    """Split ``short_comments`` by newline, parse each, and insert into the comments table."""
    if not raw_comments:
        return

    for line in raw_comments.split("\n"):
        line = line.strip()
        if line:
            parsed = _parse_comment_line(line)
            cur.execute(
                INSERT_COMMENT_SQL,
                (
                    movie_id,
                    parsed["user"],
                    parsed["rating"],
                    parsed["comment_time"],
                    parsed["helpful"],
                    parsed["comment"],
                ),
            )
