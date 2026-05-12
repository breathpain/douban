"""数据访问层：将电影和短评写入 MySQL。"""

from __future__ import annotations

import re

from .config import MySQLConfig
from .database import create_tables, drop_tables, get_connection, init_database


def save_movies_with_comments(
    cfg: MySQLConfig, items: list[dict], *, recreate: bool = False
) -> int:
    """
    将电影记录（及其短评）写入 MySQL。

    Parameters
    ----------
    cfg : MySQLConfig
        数据库连接设置。
    items : list[dict]
        由 ``DoubanItem.to_dict()`` 生成的电影字典列表。
    recreate : bool
        如果为 True，入库前先删除并重建表（用于全量导入）。
        如果为 False，检查 URL 是否存在并跳过重复数据（用于增量爬取）。

    返回实际插入的电影数量（不含重复数据）。
    """
    init_database(cfg)
    if recreate:
        drop_tables(cfg)
        create_tables(cfg)
    else:
        create_tables(cfg)

    conn = get_connection(cfg)
    inserted = 0
    try:
        with conn.cursor() as cur:
            for item in items:
                if not recreate and _movie_exists(cur, item.get("url", "")):
                    continue
                movie_id = _upsert_movie(cur, item)
                if movie_id:
                    inserted += 1
                    _save_comments(cur, movie_id, item.get("short_comments", ""))
        conn.commit()
    finally:
        conn.close()

    return inserted


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def _movie_exists(cur, url: str) -> bool:
    """检查给定 URL 的电影是否已存在，返回 True 表示已存在。"""
    cur.execute("SELECT 1 FROM movies WHERE url = %s", (url,))
    return cur.fetchone() is not None


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
    """插入或更新一条电影记录，返回其 id（失败则返回 None）。"""

    # 仅保留与 movies 表列匹配的字段
    fields = {
        "rank": item.get("rank"),
        "title": (item.get("title") or "")[:255],
        "title_cn": (item.get("title_cn") or "")[:255],
        "title_en": (item.get("title_en") or "")[:255],
        "url": (item.get("url") or "")[:512],
        "rating": item.get("rating"),
        "comment_count": item.get("comment_count"),
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
    将一行原始评论字符串解析为组成部分字段。

    预期格式：
        用户：xxx | 评分：xxx | 时间：xxx | 有用：xxx | 评论：xxx
    某些字段（如评分）可能不出现。
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
    """将 ``short_comments`` 按换行符拆分，逐条解析并写入 comments 表。"""
    if not raw_comments:
        return

    seen: set[tuple[str, str, str]] = set()
    for line in raw_comments.split("\n"):
        line = line.strip()
        if not line:
            continue
        parsed = _parse_comment_line(line)
        key = (parsed["user"], parsed["comment_time"], parsed["comment"])
        if key in seen:
            continue
        seen.add(key)

        # 将 helpful 转为 int（空值则为 None）
        helpful_raw = parsed["helpful"].strip()
        helpful_val: int | None = int(helpful_raw) if helpful_raw else None

        cur.execute(
            INSERT_COMMENT_SQL,
            (
                movie_id,
                parsed["user"],
                parsed["rating"],
                parsed["comment_time"],
                helpful_val,
                parsed["comment"],
            ),
        )
