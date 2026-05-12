"""将 MySQL 数据导出为 JSON / CSV 备份文件。"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from .config import MySQLConfig
from .database import get_dict_connection


def export_backup(cfg: MySQLConfig) -> tuple[Path, Path, Path]:
    """
    从 MySQL 读取所有电影和短评数据，写出备份文件。

    返回 (json_path, movies_csv_path, comments_csv_path)。
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
    """获取所有电影行，并将对应短评作为嵌套字典列表附加到每部电影上。"""
    conn = get_dict_connection(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM movies ORDER BY id")
            movies = [_convert_decimal_row(row) for row in cur.fetchall()]

            cur.execute(
                "SELECT movie_id, `user`, rating, comment_time, helpful, comment "
                "FROM comments ORDER BY id"
            )
            comments_by_movie: dict[int, list[dict[str, Any]]] = {}
            for row in cur.fetchall():
                comment_dict = {
                    "user": row["user"],
                    "rating": row["rating"],
                    "comment_time": row["comment_time"],
                    "helpful": row["helpful"],
                    "comment": row["comment"],
                }
                comments_by_movie.setdefault(row["movie_id"], []).append(comment_dict)

        for movie in movies:
            movie["comments"] = comments_by_movie.get(movie["id"], [])
            if "created_at" in movie and hasattr(movie["created_at"], "isoformat"):
                movie["created_at"] = movie["created_at"].isoformat()

        return movies
    finally:
        conn.close()


def _convert_decimal_row(row: dict[str, Any]) -> dict[str, Any]:
    """将 Decimal 值转为 float，使行数据可被 JSON 序列化。"""
    return {
        k: float(v) if isinstance(v, Decimal) else v
        for k, v in row.items()
    }


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
    fieldnames = ["movie_id", "title", "user", "rating", "comment_time", "helpful", "comment"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for movie in movies:
            for comment in movie.get("comments", []):
                writer.writerow({
                    "movie_id": movie["id"],
                    "title": movie["title"],
                    "user": comment["user"],
                    "rating": comment["rating"],
                    "comment_time": comment["comment_time"],
                    "helpful": comment["helpful"],
                    "comment": comment["comment"],
                })
