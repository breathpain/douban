#!/usr/bin/env python3
"""Scrapy 豆瓣爬虫的便捷启动脚本。

用法（在项目根目录执行）::

    # 爬取 Top250
    python run_scrapy_spider.py --spider top250 --max-pages 1

    # 自定义 URL
    python run_scrapy_spider.py --spider custom --urls "https://movie.douban.com/top250?start=0"

    # 所有选项
    python run_scrapy_spider.py --spider top250 --max-pages 2 --comment-limit 10 --no-details
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run Scrapy Douban spider")
    p.add_argument("--spider", choices=("top250", "custom"), default="top250")
    p.add_argument("--max-pages", type=int, default=None, help="Override max pages")
    p.add_argument("--comment-limit", type=int, default=None, help="Override comment limit")
    p.add_argument("--no-details", action="store_true", help="Skip detail pages")
    p.add_argument("--urls", default="", help="Custom URLs (comma-separated, for --spider custom)")
    p.add_argument("--output-dir", default=None, help="Export output directory")
    p.add_argument("--no-images", action="store_true", help="Skip image download")
    p.add_argument("--cookie", default=None, help="Douban cookie string")
    p.add_argument("--proxy", default=None, help="Proxy URL (http://...)")
    return p


def main() -> None:
    args = build_parser().parse_args()

    # 确保项目根目录和 scrapy_douban 包目录都在 sys.path 中
    project_root = Path(__file__).resolve().parent
    scrapy_project_dir = project_root / "scrapy_douban"
    for p in [str(project_root), str(scrapy_project_dir)]:
        if p not in sys.path:
            sys.path.insert(0, p)

    from scrapy.utils.project import get_project_settings
    from scrapy.crawler import CrawlerProcess

    os = __import__("os")

    # 从 scrapy_douban.settings 加载默认配置
    os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "scrapy_douban.settings")
    settings = get_project_settings()

    # 应用命令行参数覆盖
    if args.max_pages is not None:
        settings.set("MAX_PAGES", args.max_pages)
    if args.comment_limit is not None:
        settings.set("COMMENT_LIMIT", args.comment_limit)
    if args.no_details:
        settings.set("CRAWL_DETAILS", False)
    if args.no_images:
        settings.set("DOWNLOAD_IMAGES", False)
    if args.cookie:
        settings.set("DOUBAN_COOKIE", args.cookie)
    if args.proxy:
        settings.set("PROXY", args.proxy)
    if args.output_dir:
        settings.set("EXPORT_DIR", args.output_dir)

    process = CrawlerProcess(settings)

    if args.spider == "top250":
        process.crawl("top250")
    else:
        if not args.urls:
            raise SystemExit("--spider custom requires --urls (comma-separated)")
        process.crawl("custom", urls=args.urls)

    process.start()


if __name__ == "__main__":
    main()
