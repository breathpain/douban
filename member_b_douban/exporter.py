"""Export MySQL data to JSON / CSV backup files."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .config import MySQLConfig
from .database import get_dict_connection


def export_backup(cfg: MySQLConfig) -> tuple[Path, Path, Path]:
    """
    Read all movies and comments from MySQL and write backup files.

    Returns (json_path, movies_csv_path, comments_csv_path).
    """
    movies = _fetch_movies_with_comments(cfg)

    output_dir = Path(cfg.backup_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- JSON (nested) ---
    json_path = output_dir / "douban_movies.json"
    json_path.write_text(
        json.dumps(movies, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # --- CSV: movies ---
    movies_csv_path = output_dir / "douban_movies.csv"
    _write_movies_csv(movies, movies_csv_path)

    # --- CSV: comments ---
    comments_csv_path = output_dir / "douban_comments.csv"
    _write_comments_csv(movies, comments_csv_path)

    return json_path, movies_csv_path, comments_csv_path


def _fetch_movies_with_comments(cfg: MySQLConfig) -> list[dict[str, Any]]:
    """Fetch every movie row and attach its comments as a nested list."""
    conn = get_dict_connection(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM movies ORDER BY id")
            movies = list(cur.fetchall())

            cur.execute("SELECT movie_id, raw_comment FROM comments ORDER BY id")
            comments_by_movie: dict[int, list[str]] = {}
            for row in cur.fetchall():
                comments_by_movie.setdefault(row["movie_id"], []).append(
                    row["raw_comment"]
                )

        for movie in movies:
            movie["comments"] = comments_by_movie.get(movie["id"], [])
            if "created_at" in movie and hasattr(movie["created_at"], "isoformat"):
                movie["created_at"] = movie["created_at"].isoformat()

        return movies
    finally:
        conn.close()


def _write_movies_csv(movies: list[dict[str, Any]], path: Path) -> None:
    if not movies:
        return

    fieldnames = [k for k in movies[0].keys() if k != "comments"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for movie in movies:
            row = {k: v for k, v in movie.items() if k != "comments"}
            writer.writerow(row)


def _write_comments_csv(movies: list[dict[str, Any]], path: Path) -> None:
    fieldnames = ["movie_id", "title", "raw_comment"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for movie in movies:
            for comment in movie.get("comments", []):
                writer.writerow({
                    "movie_id": movie["id"],
                    "title": movie["title"],
                    "raw_comment": comment,
                })
