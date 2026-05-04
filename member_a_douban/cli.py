"""Command line entry point for member A."""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from .cleaner import clean_items
from .config import CrawlConfig
from .crawler import DoubanCrawler, expand_paginated_urls, save_items
from .parser import DoubanItem


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Member A Douban crawler")
    parser.add_argument(
        "--mode",
        choices=("top250", "urls"),
        default="top250",
        help="Crawl Douban movie Top250 or custom URLs.",
    )
    parser.add_argument("--url", action="append", default=[], help="Custom Douban URL.")
    parser.add_argument("--max-pages", type=int, default=10, help="Maximum pages to crawl.")
    parser.add_argument("--output-dir", default="data/member_a", help="Output directory.")
    parser.add_argument("--cookie", default=None, help="Optional Douban cookie string for public requests.")
    parser.add_argument(
        "--proxy",
        action="append",
        default=[],
        help=(
            "Proxy URL, for example http://127.0.0.1:7890. "
            "Can be repeated to rotate proxies."
        ),
    )
    parser.add_argument(
        "--page-param",
        default="start",
        help="Query parameter used for custom URL pagination, such as start or page.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=25,
        help="Offset step for start-style pagination.",
    )
    parser.add_argument("--use-selenium", action="store_true", help="Enable Selenium fallback.")
    parser.add_argument("--show-browser", action="store_true", help="Run Selenium with visible Chrome.")
    parser.add_argument("--driver-path", default=None, help="Path to chromedriver.exe.")
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Use a faster preset for demos: 4 detail workers, 6 image workers, 0.5-1.5s delay.",
    )
    parser.add_argument("--no-images", action="store_true", help="Skip image download.")
    parser.add_argument("--no-details", action="store_true", help="Skip movie detail pages.")
    parser.add_argument(
        "--comment-limit",
        type=int,
        default=15,
        help="Short comments to crawl for each movie. Use 0 to skip comments.",
    )
    parser.add_argument(
        "--detail-workers",
        type=int,
        default=1,
        help="Concurrent workers for movie detail and comment pages. Selenium mode stays sequential.",
    )
    parser.add_argument(
        "--image-workers",
        type=int,
        default=1,
        help="Concurrent workers for poster downloads.",
    )
    parser.add_argument("--delay-min", type=float, default=1.0, help="Minimum delay seconds.")
    parser.add_argument("--delay-max", type=float, default=4.0, help="Maximum delay seconds.")
    return parser


def _build_proxy_pool(proxy_urls: list[str]) -> tuple[dict[str, str], ...]:
    proxies = []
    for proxy_url in proxy_urls:
        proxy_url = proxy_url.strip()
        if not proxy_url:
            continue
        proxies.append({"http": proxy_url, "https": proxy_url})
    return tuple(proxies)

def main() -> None:
    args = build_parser().parse_args()
    start_time = time.perf_counter()
    output_dir = Path(args.output_dir)
    proxy_pool = _build_proxy_pool(args.proxy)
    detail_workers = max(1, args.detail_workers)
    image_workers = max(1, args.image_workers)
    delay_min = args.delay_min
    delay_max = args.delay_max
    config = CrawlConfig(
        output_dir=output_dir,
        image_dir=output_dir / "images",
        max_pages=args.max_pages,
        page_param=args.page_param,
        page_size=max(1, args.page_size),
        proxies=proxy_pool[0] if len(proxy_pool) == 1 else None,
        proxy_pool=proxy_pool if len(proxy_pool) > 1 else (),
        cookie=args.cookie,
        use_selenium=args.use_selenium,
        selenium_headless=not args.show_browser,
        chrome_driver_path=args.driver_path,
        download_images=not args.no_images,
        crawl_details=not args.no_details,
        comment_limit=max(0, args.comment_limit),
        detail_workers=detail_workers,
        image_workers=image_workers,
        delay_min=delay_min,
        delay_max=delay_max,
    )

    if args.mode == "import":
        _run_import(config.output_dir, args.save_mysql)
        return

    crawler = DoubanCrawler(config)
    if args.mode == "urls":
        if not args.url:
            raise SystemExit("--mode urls requires at least one --url")
        items = crawler.crawl_urls(args.url)
    else:
        items = crawler.crawl_movie_top250()

    clean_items(items)
    json_path, csv_path = save_items(items, config.output_dir)

    if args.save_mysql:
        _save_to_mysql(items)

    elapsed = time.perf_counter() - start_time
    avg_time = elapsed / len(items) if items else 0
    print(f"saved {len(items)} items")
    print(f"json: {json_path}")
    print(f"csv: {csv_path}")
    if args.save_mysql:
        print(f"saved {len(items)} items into MySQL")
        print(f"backup exported to data/member_b/backup/")
    print(f"elapsed: {elapsed:.2f}s")
    print(f"avg per item: {avg_time:.2f}s")


def _run_import(output_dir: Path, save_mysql: bool) -> None:
    """Import items from local JSON/CSV and optionally write to MySQL."""
    json_path = output_dir / "douban_items.json"
    csv_path = output_dir / "douban_items.csv"

    if json_path.exists():
        with json_path.open("r", encoding="utf-8") as f:
            raw_data = json.load(f)
    elif csv_path.exists():
        with csv_path.open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            raw_data = list(reader)
    else:
        raise SystemExit(f"no data file found at {output_dir}/douban_items.json or .csv")

    items = []
    for d in raw_data:
        # Convert empty runtime strings back to None
        if "runtime" in d and d["runtime"] == "":
            d["runtime"] = None
        items.append(DoubanItem(**d))

    clean_items(items)
    print(f"loaded {len(items)} items from {json_path if json_path.exists() else csv_path}")

    if save_mysql:
        _save_to_mysql(items)


def _save_to_mysql(items: list[DoubanItem]) -> int:
    """Save cleaned DoubanItem list into MySQL and export backups."""
    try:
        from member_b_douban import save_to_mysql

        inserted = save_to_mysql([item.to_dict() for item in items])
        print(f"saved {inserted} items into MySQL")
        print(f"backup exported to data/member_b/backup/")
        return inserted
    except ImportError as exc:
        raise SystemExit(
            "member_b_douban package not available; "
            "ensure it is in the Python path."
        ) from exc


if __name__ == "__main__":
    main()
