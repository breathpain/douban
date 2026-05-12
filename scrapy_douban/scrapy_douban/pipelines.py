"""豆瓣 Scrapy 爬虫的 Item 管道。

管道（按顺序）：
1. ``CleaningPipeline`` – 规范化数字字段（复用 ``cleaner.py``）
2. ``ImageDownloadPipeline`` – 下载海报图片
3. ``ExportPipeline`` – 爬虫关闭时将数据持久化为 JSON + CSV
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from scrapy import Spider, signals

try:
    from requests_douban.cleaner import clean_items as _clean_parser_items
    from requests_douban.image_downloader import download_image
    from requests_douban.parser import DoubanItem as ParserItem
except ImportError:
    ParserItem = None  # type: ignore[assignment]

    def _clean_parser_items(items):  # type: ignore[no-untyped-def]
        return items

    def download_image(  # type: ignore[no-redef]
        url: str, output_dir: Path, config, filename_stem: str | None = None
    ) -> Path | None:
        return None


# ---------------------------------------------------------------------------
# 辅助函数：Scrapy Item ↔ Parser 数据类 Item 互转
# ---------------------------------------------------------------------------

def _scrapy_item_to_parser_dict(scrapy_item) -> dict[str, Any]:
    """将 Scrapy ``DoubanItem`` 转为普通字典以进行清洗。"""
    result: dict[str, Any] = {}
    for k in scrapy_item.fields:
        result[k] = scrapy_item.get(k)
    return result


def _dict_to_parser_item(data: dict[str, Any]) -> Any:
    """从字典重建 parser ``DoubanItem``，以便清洗器处理。"""
    if ParserItem is None:
        return data
    title = data.get("title") or ""
    url = data.get("url") or ""
    item = ParserItem(title=title, url=url)
    for f in item.__dataclass_fields__:  # type: ignore[union-attr]
        val = data.get(f)
        if val is not None:
            setattr(item, f, val)
    return item


# ---------------------------------------------------------------------------
# 管道 1：数据清洗
# ---------------------------------------------------------------------------

class CleaningPipeline:
    """应用与 requests 版本相同的清洗转换。"""

    def process_item(self, item, spider: Spider) -> Any:
        data = _scrapy_item_to_parser_dict(item)
        parser_item = _dict_to_parser_item(data)
        _clean_parser_items([parser_item])

        # 将清洗后的值写回 Scrapy Item
        cleaned = asdict(parser_item) if hasattr(parser_item, "__dataclass_fields__") else data
        for k in item.fields:
            if k in cleaned:
                item[k] = cleaned[k]
        return item


# ---------------------------------------------------------------------------
# 管道 2：图片下载
# ---------------------------------------------------------------------------

class ImageDownloadPipeline:
    """为每个条目下载海报图片。

    当 ``settings.DOWNLOAD_IMAGES`` 为 ``False`` 时跳过。
    """

    def __init__(self, enabled: bool, image_dir: str | None) -> None:
        self.enabled = enabled
        self.image_dir = Path(image_dir) if image_dir else None

    @classmethod
    def from_crawler(cls, crawler) -> ImageDownloadPipeline:
        enabled = crawler.settings.getbool("DOWNLOAD_IMAGES", True)
        image_dir = crawler.settings.get("IMAGES_STORE") or "data/crawler/images"
        return cls(enabled, image_dir)

    def process_item(self, item, spider: Spider) -> Any:
        if not self.enabled or not item.get("image_url"):
            return item

        image_url = item["image_url"]
        filename_stem = item.get("title") or None

        from requests_douban.config import CrawlConfig as _Cfg
        # 为 image_downloader 构建一个最小配置
        cfg = _Cfg(
            image_dir=self.image_dir or Path("data/crawler/images"),
            proxies=None,
            proxy_pool=(),
            user_agents=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",),
        )
        path = download_image(image_url, self.image_dir, cfg, filename_stem)
        if path:
            item["image_file"] = str(path)
        return item


# ---------------------------------------------------------------------------
# 管道 3：导出 JSON / CSV
# ---------------------------------------------------------------------------

class ExportPipeline:
    """累积条目，在爬虫关闭时将数据写为 JSON + CSV。

    输出文件写入 ``settings.EXPORT_DIR``（默认 ``data/crawler``），
    文件名为 ``douban_items.json`` 和 ``douban_items.csv``。
    """

    def __init__(self, export_dir: str) -> None:
        self.export_dir = Path(export_dir)
        self.items: list[dict[str, Any]] = []

    @classmethod
    def from_crawler(cls, crawler) -> ExportPipeline:
        export_dir = crawler.settings.get("EXPORT_DIR", "data/crawler")
        pipeline = cls(export_dir)

        # 连接到 spider_closed 信号
        crawler.signals.connect(pipeline.spider_closed, signal=signals.spider_closed)
        return pipeline

    def process_item(self, item, spider: Spider) -> Any:
        data: dict[str, Any] = {}
        for k in item.fields:
            data[k] = item.get(k)
        self.items.append(data)
        return item

    def spider_closed(self, spider: Spider) -> None:
        if not self.items:
            spider.logger.warning("No items collected, skipping export.")
            return

        self.export_dir.mkdir(parents=True, exist_ok=True)
        json_path = self.export_dir / "douban_items.json"
        csv_path = self.export_dir / "douban_items.csv"

        # --- JSON ---
        json_path.write_text(
            json.dumps(self.items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        spider.logger.info("Exported %d items to %s", len(self.items), json_path)

        # --- CSV ---
        fieldnames = list(self.items[0].keys())
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.items)
        spider.logger.info("Exported %d items to %s", len(self.items), csv_path)
