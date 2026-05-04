"""High-level Douban crawler workflow."""

from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode

from .anti_spider import polite_sleep
from .config import CrawlConfig
from .http_client import BlockedByDoubanError, DoubanHttpClient, HttpResult
from .image_downloader import download_image
from .parser import (
    DoubanItem,
    enrich_movie_detail,
    has_movie_detail_info,
    parse_douban_items,
    parse_movie_comments,
)
from .selenium_renderer import SeleniumRenderer


class DoubanCrawler:
    def __init__(self, config: CrawlConfig) -> None:
        self.config = config
        self.client = DoubanHttpClient(config)

    def crawl_urls(self, urls: list[str]) -> list[DoubanItem]:
        all_items: list[DoubanItem] = []
        renderer: SeleniumRenderer | None = None

        try:
            if self.config.use_selenium:
                renderer = SeleniumRenderer(self.config).__enter__()

            for url in urls[: self.config.max_pages]:
                result = self._fetch(url, renderer)
                items = parse_douban_items(result.text, result.url)
                if self.config.crawl_details:
                    self._crawl_details(items, renderer)
                if self.config.download_images:
                    self._download_images(items)
                all_items.extend(items)
        finally:
            if renderer:
                renderer.__exit__(None, None, None)

        return all_items

    def crawl_movie_top250(self) -> list[DoubanItem]:
        urls = [
            "https://movie.douban.com/top250?" + urlencode({"start": page * 25})
            for page in range(self.config.max_pages)
        ]
        return self.crawl_urls(urls)

    def _fetch(
        self,
        url: str,
        renderer: SeleniumRenderer | None,
        client: DoubanHttpClient | None = None,
    ) -> HttpResult:
        http_client = client or self.client
        try:
            return http_client.get(url)
        except (RuntimeError, BlockedByDoubanError):
            if renderer is None:
                raise
            return renderer.render(url)

    def _download_images(self, items: list[DoubanItem]) -> None:
        for item in items:
            try:
                path = download_image(
                    item.image_url,
                    self.config.image_dir,
                    self.config,
                    item.title,
                )
            except Exception:
                path = None
            if path:
                item.image_file = str(path)

    def _crawl_details(self, items: list[DoubanItem], renderer: SeleniumRenderer | None) -> None:
        if renderer is None and self.config.detail_workers > 1:
            self._crawl_details_concurrently(items)
            return

        for item in items:
            self._crawl_detail_item(item, renderer)
            polite_sleep(self.config.delay_min, self.config.delay_max)

    def _crawl_details_concurrently(self, items: list[DoubanItem]) -> None:
        with ThreadPoolExecutor(max_workers=self.config.detail_workers) as executor:
            futures = {
                executor.submit(
                    self._crawl_detail_item_with_delay,
                    item,
                    DoubanHttpClient(self.config),
                ): item
                for item in items
                if item.url
            }
            for future in as_completed(futures):
                item = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    item.detail_error = str(exc)

    def _crawl_detail_item_with_delay(
        self,
        item: DoubanItem,
        client: DoubanHttpClient,
    ) -> None:
        try:
            self._crawl_detail_item(item, None, client)
        finally:
            polite_sleep(self.config.delay_min, self.config.delay_max)

    def _crawl_detail_item(
        self,
        item: DoubanItem,
        renderer: SeleniumRenderer | None,
        client: DoubanHttpClient | None = None,
    ) -> None:
        if not item.url:
            return
        try:
            result = self._fetch(item.url, renderer, client)
            if renderer and not has_movie_detail_info(result.text):
                result = renderer.render(item.url)
            enrich_movie_detail(item, result.text)
            self._crawl_comments(item, result.text, renderer, client)
        except Exception as exc:
            item.detail_error = str(exc)

    def _crawl_comments(
        self,
        item: DoubanItem,
        detail_html: str,
        renderer: SeleniumRenderer | None,
        client: DoubanHttpClient | None = None,
    ) -> None:
        if self.config.comment_limit <= 0:
            return

        comments = parse_movie_comments(detail_html, self.config.comment_limit)
        if len(comments) < self.config.comment_limit:
            comments_url = item.url.rstrip("/") + "/comments?" + urlencode(
                {"limit": self.config.comment_limit, "status": "P", "sort": "new_score"}
            )
            try:
                result = self._fetch(comments_url, renderer, client)
                comments = parse_movie_comments(result.text, self.config.comment_limit)
            except Exception as exc:
                if not item.detail_error:
                    item.detail_error = f"comments error: {exc}"

        item.short_comments = "\n".join(comments[: self.config.comment_limit])


def save_items(items: list[DoubanItem], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "douban_items.json"
    csv_path = output_dir / "douban_items.csv"

    rows = [item.to_dict() for item in items]
    with json_path.open("w", encoding="utf-8") as file:
        json.dump(rows, file, ensure_ascii=False, indent=2)

    fieldnames = list(rows[0].keys()) if rows else list(DoubanItem("", "").to_dict().keys())
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return json_path, csv_path
