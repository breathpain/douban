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
        choices=("top250", "urls", "import"),
        default="top250",
        help="Crawl mode (top250 / urls) or import existing JSON/CSV files into MySQL.",
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
    parser.add_argument(
        "--comment-limit",
        type=int,
        default=3,
        help="Short comments to crawl for each movie. Use 0 to skip comments.",
    )
    parser.add_argument("--delay-min", type=float, default=1.2, help="Minimum delay seconds.")
    parser.add_argument("--delay-max", type=float, default=3.5, help="Maximum delay seconds.")
    parser.add_argument("--save-mysql", action="store_true", help="Store results into MySQL.")
    parser.add_argument("--mysql-host", default="localhost", help="MySQL host.")
    parser.add_argument("--mysql-port", type=int, default=3306, help="MySQL port.")
    parser.add_argument("--mysql-user", default="root", help="MySQL user.")
    parser.add_argument("--mysql-password", default="123456", help="MySQL password.")
    parser.add_argument("--mysql-database", default="douban", help="MySQL database name.")
    parser.add_argument("--mysql-backup-dir", default="data/member_b/backup", help="MySQL backup dir.")
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
        comment_limit=max(0, args.comment_limit),
        delay_min=args.delay_min,
        delay_max=args.delay_max,
    )

    crawler = DoubanCrawler(config)
    if args.mode == "urls":
        if not args.url:
            raise SystemExit("--mode urls requires at least one --url")
        items = crawler.crawl_urls(args.url)
    elif args.mode == "import":
        items = []
        json_file = output_dir / "douban_items.json"
        if not json_file.exists():
            raise SystemExit(f"JSON file not found: {json_file}")
        import json as _json
        rows = _json.loads(json_file.read_text(encoding="utf-8"))
        from .parser import DoubanItem
        for row in rows:
            item = DoubanItem(title=row.get("title", ""), url=row.get("url", ""))
            for key, val in row.items():
                if hasattr(item, key):
                    setattr(item, key, val or "")
            items.append(item)
        print(f"loaded {len(items)} items from {json_file}")
        json_path, csv_path = save_items(items, config.output_dir)
        print(f"json: {json_path}")
        print(f"csv: {csv_path}")
    else:
        items = crawler.crawl_movie_top250()
        json_path, csv_path = save_items(items, config.output_dir)
        print(f"saved {len(items)} items")
        print(f"json: {json_path}")
        print(f"csv: {csv_path}")

    if args.save_mysql:
        try:
            from member_b_douban import save_to_mysql as member_b_save

            inserted = member_b_save(
                [item.to_dict() for item in items],
                host=args.mysql_host,
                port=args.mysql_port,
                user=args.mysql_user,
                password=args.mysql_password,
                database=args.mysql_database,
                backup_dir=args.mysql_backup_dir,
            )
            print(f"MySQL: inserted {inserted} movies (with comments)")
            print(f"MySQL backup dir: {args.mysql_backup_dir}")
        except ImportError:
            print("Warning: pymysql not installed. Run: pip install pymysql")
        except Exception as exc:
            print(f"MySQL error: {exc}")


if __name__ == "__main__":
    main()
