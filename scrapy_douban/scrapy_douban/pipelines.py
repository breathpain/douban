"""Item pipelines for the Douban Scrapy crawler.

Pipelines (in order):
1. ``CleaningPipeline`` – normalise numeric fields (reuse ``cleaner.py``)
2. ``ImageDownloadPipeline`` – download poster images
3. ``ExportPipeline`` – persist items as JSON + CSV on spider close
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from scrapy import Spider, signals

try:
    from member_a_douban.cleaner import clean_items as _clean_parser_items
    from member_a_douban.image_downloader import download_image
    from member_a_douban.parser import DoubanItem as ParserItem
except ImportError:
    ParserItem = None  # type: ignore[assignment]

    def _clean_parser_items(items):  # type: ignore[no-untyped-def]
        return items

    def download_image(  # type: ignore[no-redef]
        url: str, output_dir: Path, config, filename_stem: str | None = None
    ) -> Path | None:
        return None


# ---------------------------------------------------------------------------
# Helper: convert Scrapy Item <-> Parser dataclass Item
# ---------------------------------------------------------------------------

def _scrapy_item_to_parser_dict(scrapy_item) -> dict[str, Any]:
    """Convert a Scrapy ``DoubanItem`` into a plain dict for cleaning."""
    result: dict[str, Any] = {}
    for k in scrapy_item.fields:
        result[k] = scrapy_item.get(k)
    return result


def _dict_to_parser_item(data: dict[str, Any]) -> Any:
    """Rebuild a parser ``DoubanItem`` from a dict so cleaner can handle it."""
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
# Pipeline 1: Cleaning
# ---------------------------------------------------------------------------

class CleaningPipeline:
    """Apply the same cleaning transforms as the requests version."""

    def process_item(self, item, spider: Spider) -> Any:
        data = _scrapy_item_to_parser_dict(item)
        parser_item = _dict_to_parser_item(data)
        _clean_parser_items([parser_item])

        # Write cleaned values back to the Scrapy Item
        cleaned = asdict(parser_item) if hasattr(parser_item, "__dataclass_fields__") else data
        for k in item.fields:
            if k in cleaned:
                item[k] = cleaned[k]
        return item


# ---------------------------------------------------------------------------
# Pipeline 2: Image Download
# ---------------------------------------------------------------------------

class ImageDownloadPipeline:
    """Download poster images for each item.

    Skipped when ``settings.DOWNLOAD_IMAGES`` is ``False``.
    """

    def __init__(self, enabled: bool, image_dir: str | None) -> None:
        self.enabled = enabled
        self.image_dir = Path(image_dir) if image_dir else None

    @classmethod
    def from_crawler(cls, crawler) -> ImageDownloadPipeline:
        enabled = crawler.settings.getbool("DOWNLOAD_IMAGES", True)
        image_dir = crawler.settings.get("IMAGES_STORE") or "data/member_a/images"
        return cls(enabled, image_dir)

    def process_item(self, item, spider: Spider) -> Any:
        if not self.enabled or not item.get("image_url"):
            return item

        image_url = item["image_url"]
        filename_stem = item.get("title") or None

        from member_a_douban.config import CrawlConfig as _Cfg
        # Build a minimal config for image_downloader
        cfg = _Cfg(
            image_dir=self.image_dir or Path("data/member_a/images"),
            proxies=None,
            proxy_pool=(),
            user_agents=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",),
        )
        path = download_image(image_url, self.image_dir, cfg, filename_stem)
        if path:
            item["image_file"] = str(path)
        return item


# ---------------------------------------------------------------------------
# Pipeline 3: Export JSON / CSV
# ---------------------------------------------------------------------------

class ExportPipeline:
    """Accumulate items and write JSON + CSV on spider close.

    Output files are written to ``settings.EXPORT_DIR`` (default
    ``data/member_a``) as ``douban_items.json`` and ``douban_items.csv``.
    """

    def __init__(self, export_dir: str) -> None:
        self.export_dir = Path(export_dir)
        self.items: list[dict[str, Any]] = []

    @classmethod
    def from_crawler(cls, crawler) -> ExportPipeline:
        export_dir = crawler.settings.get("EXPORT_DIR", "data/member_a")
        pipeline = cls(export_dir)

        # Connect to spider_closed signal
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
