"""Command line entry point for member A."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import CrawlConfig
from .crawler import DoubanCrawler, save_items


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Member A Douban crawler")
    parser.add_argument(
        "--mode",
        choices=("top250", "urls"),
        default="top250",
        help="Crawl Douban movie Top250 or custom URLs.",
    )
    parser.add_argument("--url", action="append", default=[], help="Custom Douban URL.")
    parser.add_argument("--max-pages", type=int, default=1, help="Maximum pages to crawl.")
    parser.add_argument("--output-dir", default="data/member_a", help="Output directory.")
    parser.add_argument("--cookie", default=None, help="Douban cookie string for logged-in pages.")
    parser.add_argument("--use-selenium", action="store_true", help="Enable Selenium fallback.")
    parser.add_argument("--show-browser", action="store_true", help="Run Selenium with visible Chrome.")
    parser.add_argument("--driver-path", default=None, help="Path to chromedriver.exe.")
    parser.add_argument("--no-images", action="store_true", help="Skip image download.")
    parser.add_argument("--no-details", action="store_true", help="Skip movie detail pages.")
    parser.add_argument("--delay-min", type=float, default=1.2, help="Minimum delay seconds.")
    parser.add_argument("--delay-max", type=float, default=3.5, help="Maximum delay seconds.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    config = CrawlConfig(
        output_dir=output_dir,
        image_dir=output_dir / "images",
        max_pages=args.max_pages,
        cookie=args.cookie,
        use_selenium=args.use_selenium,
        selenium_headless=not args.show_browser,
        chrome_driver_path=args.driver_path,
        download_images=not args.no_images,
        crawl_details=not args.no_details,
        delay_min=args.delay_min,
        delay_max=args.delay_max,
    )

    crawler = DoubanCrawler(config)
    if args.mode == "urls":
        if not args.url:
            raise SystemExit("--mode urls requires at least one --url")
        items = crawler.crawl_urls(args.url)
    else:
        items = crawler.crawl_movie_top250()

    json_path, csv_path = save_items(items, config.output_dir)
    print(f"saved {len(items)} items")
    print(f"json: {json_path}")
    print(f"csv: {csv_path}")


if __name__ == "__main__":
    main()
