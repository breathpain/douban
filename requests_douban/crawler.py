"""豆瓣爬虫高层工作流。"""

from __future__ import annotations

import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    from tqdm import tqdm
except ModuleNotFoundError:  # pragma: no cover - optional runtime fallback
    def tqdm(iterable, **kwargs):  # type: ignore[no-redef]
        return iterable

from .anti_spider import polite_sleep
from .config import CrawlConfig
from .http_client import BlockedByDoubanError, DoubanHttpClient, HttpResult
from .image_downloader import download_image
from .parser import (
    DoubanItem,
    enrich_movie_detail,
    has_movie_detail_info,
    has_next_page,
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
            # 当配置了 chromedriver 路径时也自动启用 Selenium（应对详情页 sec.douban.com 安全验证）
            if self.config.use_selenium or self.config.chrome_driver_path:
                renderer = SeleniumRenderer(self.config).__enter__()

            for url in tqdm(urls, desc="list pages", unit="page"):
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

        # 全局去重：基于 URL 去重（同一电影可能在不同列表页出现）
        return _deduplicate_items(all_items)

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
        referer: str | None = None,
    ) -> HttpResult:
        http_client = client or self.client
        try:
            return http_client.get(url, referer=referer)
        except (RuntimeError, BlockedByDoubanError):
            if renderer is None:
                raise
            return renderer.render(url)

    def _download_images(self, items: list[DoubanItem]) -> None:
        if self.config.image_workers > 1:
            self._download_images_concurrently(items)
            return

        for item in tqdm(items, desc="posters", unit="image", leave=False):
            self._download_image_item(item)

    def _download_images_concurrently(self, items: list[DoubanItem]) -> None:
        with ThreadPoolExecutor(max_workers=self.config.image_workers) as executor:
            futures = {
                executor.submit(self._download_image_item, item): item
                for item in items
                if item.image_url
            }
            for future in tqdm(
                as_completed(futures),
                total=len(futures),
                desc="posters",
                unit="image",
                leave=False,
            ):
                try:
                    future.result()
                except Exception:
                    continue

    def _download_image_item(self, item: DoubanItem) -> None:
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
        # Selenium 模式下不启用并发（共享浏览器实例），但可同时执行约 3-5 个详情页
        if renderer is None:
            if self.config.detail_workers > 1:
                self._crawl_details_concurrently(items)
                return
            for item in tqdm(items, desc="details/comments", unit="movie", leave=False):
                self._crawl_detail_item(item, renderer)
                polite_sleep(self.config.delay_min, self.config.delay_max)
        else:
            for item in tqdm(items, desc="details/comments", unit="movie", leave=False):
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
            for future in tqdm(
                as_completed(futures),
                total=len(futures),
                desc="details/comments",
                unit="movie",
                leave=False,
            ):
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
            result = self._fetch_detail_page(item, renderer, client)
            enrich_movie_detail(item, result.text)
            self._crawl_comments(item, result.text, renderer, client)
        except Exception as exc:
            item.detail_error = str(exc)

    def _fetch_detail_page(
        self,
        item: DoubanItem,
        renderer: SeleniumRenderer | None,
        client: DoubanHttpClient | None = None,
    ) -> HttpResult:
        try:
            result = self._fetch(item.url, renderer, client, referer=item.source_page)
            if has_movie_detail_info(result.text):
                return result
        except Exception as exc:
            desktop_error = exc
        else:
            desktop_error = RuntimeError("desktop detail page has no parseable detail info")

        mobile_url = _mobile_subject_url(item.url)
        if mobile_url:
            try:
                result = self._fetch(mobile_url, renderer, client, referer=item.url)
                if has_movie_detail_info(result.text):
                    return result
            except Exception as mobile_exc:
                raise RuntimeError(
                    f"desktop detail failed: {desktop_error}; mobile detail failed: {mobile_exc}"
                ) from mobile_exc

        raise RuntimeError(f"desktop detail failed: {desktop_error}")

    def _crawl_comments(
        self,
        item: DoubanItem,
        detail_html: str,
        renderer: SeleniumRenderer | None,
        client: DoubanHttpClient | None = None,
    ) -> None:
        if self.config.comment_limit <= 0:
            return

        base_url = item.url.rstrip("/")
        all_comments: list[str] = []
        page = 0
        movie_label = item.title[:20] if item.title else ""

        pbar = tqdm(
            total=self.config.comment_limit,
            desc=f"comments: {movie_label}" if movie_label else "comments",
            unit="cmt",
            leave=False,
        )

        while len(all_comments) < self.config.comment_limit:
            if page == 0:
                # 第一页
                comments_url = base_url + "/comments?" + urlencode({"status": "P"})
            else:
                # 后续翻页
                comments_url = base_url + "/comments?" + urlencode(
                    {
                        "start": page * 20,
                        "limit": 20,
                        "status": "P",
                        "sort": "new_score",
                    }
                )

            try:
                if renderer is not None:
                    result = renderer.render_comments(comments_url, self.config.comment_limit)
                else:
                    result = self._fetch(comments_url, renderer, client, referer=item.url)
            except Exception as exc:
                if not item.detail_error:
                    item.detail_error = f"comments error at page {page}: {exc}"
                break

            page_comments = parse_movie_comments(result.text, 999)
            if not page_comments:
                break

            # 与已收集评论去重
            all_comments = _deduplicate_comments(all_comments, page_comments)
            pbar.update(min(len(all_comments), self.config.comment_limit) - pbar.n)

            # 如果该页不满 20 条，说明已是最后一页
            if len(page_comments) < 20:
                break

            # 检查分页器是否有"后页"链接
            if not has_next_page(result.text):
                break

            page += 1
            polite_sleep(self.config.delay_min, self.config.delay_max)

        pbar.close()
        item.short_comments = "\n".join(all_comments[: self.config.comment_limit])


def save_items(items: list[DoubanItem], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "douban_items.json"
    csv_path = output_dir / "douban_items.csv"

    rows = [item.to_dict() for item in items]
    with json_path.open("w", encoding="utf-8") as file:
        json.dump(rows, file, ensure_ascii=False, indent=2)

    fieldnames = list(rows[0].keys()) if rows else list(DoubanItem("", "", "").to_dict().keys())
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return json_path, csv_path


def expand_paginated_urls(urls: list[str], config: CrawlConfig) -> list[str]:
    """将自定义 URL 按查询分页参数展开为多页 URL。"""

    expanded: list[str] = []
    for url in urls:
        expanded.extend(_expand_url(url, config.max_pages, config.page_param, config.page_size))
    return expanded


def _expand_url(url: str, max_pages: int, page_param: str, page_size: int) -> list[str]:
    if max_pages <= 1:
        return [url]

    if "{page}" in url or "{start}" in url:
        return [
            url.format(page=page + 1, start=page * page_size)
            for page in range(max_pages)
        ]

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if page_param not in query and "start" not in query and "page" not in query:
        return [url]

    param = page_param if page_param in query else ("start" if "start" in query else "page")
    first_value = int(query.get(param, "0") or 0)
    urls = []
    for page in range(max_pages):
        query[param] = str(first_value + page * page_size if param == "start" else first_value + page)
        urls.append(urlunsplit(parts._replace(query=urlencode(query))))
    return urls


def _mobile_subject_url(url: str) -> str:
    match = re.search(r"/subject/(\d+)/?", url)
    if not match:
        return ""
    return f"https://m.douban.com/movie/subject/{match.group(1)}/"


def _deduplicate_comments(
    existing: list[str], incoming: list[str]
) -> list[str]:
    """
    对两份评论列表进行去重合并。
    existing 来自详情页（detail_html），incoming 来自 comments 完整页。
    以 "评论：" 之后的文本内容为唯一标识，保留首次出现的顺序。
    """
    seen: set[str] = set()
    result: list[str] = []

    for comment in existing + incoming:
        key = _comment_key(comment)
        if key and key not in seen:
            seen.add(key)
            result.append(comment)

    return result


def _comment_key(comment: str) -> str:
    """从格式化的评论字符串中提取去重 key（评论文本）。"""
    match = re.search(r"评论：(.*)", comment)
    if match:
        text = match.group(1).strip()
        # 去除末尾标点差异
        return text.rstrip("。.!！")
    return comment.strip()


def _deduplicate_items(items: list[DoubanItem]) -> list[DoubanItem]:
    """基于 URL 对 DoubanItem 列表去重，保留首次出现的记录。"""
    seen: set[str] = set()
    result: list[DoubanItem] = []
    for item in items:
        key = item.url.rstrip("/")
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result
