"""豆瓣爬取数据的简易清洗管道。

提供对常见字段（评分、评论数、IMDb、片长）的规范化函数，
在保存到文件或数据库之前使用。
"""

from __future__ import annotations

import re
from dataclasses import fields

from .parser import DoubanItem


def clean_items(items: list[DoubanItem]) -> list[DoubanItem]:
    """对 DoubanItem 列表执行标准清洗（原地修改）。

    清洗以下字段：
      - **rank**：转为 ``int``（如 ``1``）
      - **rating**：转为 ``float``（如 ``9.7``）
      - **comment_count**：转为 ``int``（如 ``3282402``）
      - **imdb**：提取 ``ttXXXXXX`` 编号，丢弃多余文本
      - **runtime**：转为 ``int``（分钟）
    """
    for item in items:
        _clean_text_nbsp(item)
        _clean_rank(item)
        _clean_rating(item)
        _clean_comment_count(item)
        _clean_imdb(item)
        _clean_runtime(item)
    return items


# ---------------------------------------------------------------------------
# 内部清洗函数
# ---------------------------------------------------------------------------

def _clean_text_nbsp(item: DoubanItem) -> None:
    """将所有字符串字段中的不间断空格（\u00a0）替换为普通空格。"""
    for f in fields(DoubanItem):
        val = getattr(item, f.name)
        if isinstance(val, str) and "\u00a0" in val:
            setattr(item, f.name, val.replace("\u00a0", " ").strip())


def _clean_rank(item: DoubanItem) -> None:
    rank = item.rank
    if rank is None:
        return
    if isinstance(rank, int):
        return  # 已经是干净数据
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
        return  # 已经是干净数据
    count = count.strip()
    if not count:
        item.comment_count = None
        return
    # 去除千位分隔符逗号，然后提取数字
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
        return  # 已经是干净数据
    # 字符串值如 "142分钟(国际版)" 或 "142"
    runtime = runtime.strip()
    if not runtime:
        item.runtime = None
        return
    match = re.search(r"(\d+)", runtime)
    item.runtime = int(match.group(1)) if match else None
