"""Data-access layer: insert movies & comments into MySQL."""

from __future__ import annotations

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
        title, url, rating, comment_count, summary,
        image_url, source_page, image_file,
        director, screenwriter, actors, genres,
        country, language, release_date, runtime, imdb,
        detail_error
    ) VALUES (
        %(title)s, %(url)s, %(rating)s, %(comment_count)s, %(summary)s,
        %(image_url)s, %(source_page)s, %(image_file)s,
        %(director)s, %(screenwriter)s, %(actors)s, %(genres)s,
        %(country)s, %(language)s, %(release_date)s, %(runtime)s, %(imdb)s,
        %(detail_error)s
    )
    ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)
"""

INSERT_COMMENT_SQL = """
    INSERT INTO comments (movie_id, raw_comment) VALUES (%s, %s)
"""


def _upsert_movie(cur, item: dict) -> int | None:
    """Insert or update a movie; return its id (or None on failure)."""

    # Only keep fields that match the movies table columns
    fields = {
        "title": (item.get("title") or "")[:255],
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
        "runtime": (item.get("runtime") or "")[:100],
        "imdb": (item.get("imdb") or "")[:50],
        "detail_error": item.get("detail_error") or "",
    }

    cur.execute(INSERT_MOVIE_SQL, fields)
    return cur.lastrowid


def _save_comments(cur, movie_id: int, raw_comments: str) -> None:
    """Split ``short_comments`` by newline and insert each into the comments table."""
    if not raw_comments:
        return

    for line in raw_comments.split("\n"):
        line = line.strip()
        if line:
            cur.execute(INSERT_COMMENT_SQL, (movie_id, line))
