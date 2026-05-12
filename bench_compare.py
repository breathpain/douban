#!/usr/bin/env python3
"""Benchmark & comparison script: Scrapy vs Requests Douban crawlers.

Runs both crawlers on the Top250 dataset (1 page by default) and compares:
- elapsed time (total & per-item)
- items collected
- success rate (detail & comment enrichment)
- code complexity (lines of code per module)

Usage::

    python bench_compare.py --pages 1 --no-images
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

try:
    import tabulate  # optional; fallback to plain print
except ModuleNotFoundError:
    tabulate = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve(p: str) -> str:
    return str((PROJECT_ROOT / p).resolve())


def _run_requests_crawler(
    pages: int = 1,
    comment_limit: int = 5,
    no_details: bool = False,
    no_images: bool = True,
    output_dir: str = "data/bench_requests",
) -> dict[str, Any]:
    """Run the requests-based crawler as a subprocess and parse its output."""

    cmd = [
        sys.executable,
        "-m",
        "requests_douban.cli",
        "--mode",
        "top250",
        "--max-pages",
        str(pages),
        "--comment-limit",
        str(comment_limit),
        "--output-dir",
        output_dir,
    ]
    if no_details:
        cmd.append("--no-details")
    if no_images:
        cmd.append("--no-images")

    start = time.perf_counter()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=600,
    )
    elapsed = time.perf_counter() - start

    stdout = result.stdout
    stderr = result.stderr

    # Parse output lines like:
    #   saved 25 items
    #   json: data/bench_requests/douban_items.json
    #   elapsed: 12.34s
    #   avg per item: 0.49s
    items_count = 0
    elapsed_str = ""
    avg_str = ""
    for line in stdout.splitlines():
        if "saved " in line and "items" in line:
            try:
                items_count = int(line.split()[1])
            except (IndexError, ValueError):
                pass
        if "elapsed:" in line:
            elapsed_str = line.split("elapsed:")[-1].strip()
        if "avg per item:" in line:
            avg_str = line.split("avg per item:")[-1].strip()

    return {
        "engine": "requests",
        "items": items_count,
        "elapsed_s": elapsed,
        "elapsed_str": elapsed_str,
        "avg_str": avg_str,
        "stdout": stdout,
        "stderr": stderr,
    }


def _run_scrapy_crawler(
    pages: int = 1,
    comment_limit: int = 5,
    no_details: bool = False,
    no_images: bool = True,
    output_dir: str = "data/bench_scrapy",
) -> dict[str, Any]:
    """Run the Scrapy-based crawler as a subprocess and parse its output."""

    cmd = [
        sys.executable,
        _resolve("run_scrapy_spider.py"),
        "--spider",
        "top250",
        "--max-pages",
        str(pages),
        "--comment-limit",
        str(comment_limit),
        "--output-dir",
        output_dir,
    ]
    if no_details:
        cmd.append("--no-details")
    if no_images:
        cmd.append("--no-images")

    start = time.perf_counter()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=600,
    )
    elapsed = time.perf_counter() - start

    stdout = result.stdout
    stderr = result.stderr

    # Scrapy outputs log lines; look for item count.
    items_count = 0
    for line in stdout.splitlines():
        # "Exported 25 items to ..." from ExportPipeline
        if "Exported" in line and "items to" in line:
            try:
                items_count = int(line.split()[1])
            except (IndexError, ValueError):
                pass

    return {
        "engine": "Scrapy",
        "items": items_count,
        "elapsed_s": elapsed,
        "elapsed_str": f"{elapsed:.2f}s",
        "avg_str": f"{elapsed / max(items_count, 1):.2f}s" if items_count else "N/A",
        "stdout": stdout,
        "stderr": stderr,
    }


# ---------------------------------------------------------------------------
# Code complexity summary
# ---------------------------------------------------------------------------

def _count_lines(paths: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in paths:
        p = PROJECT_ROOT / path
        if p.is_file():
            try:
                counts[path] = len(p.read_text(encoding="utf-8").splitlines())
            except Exception:
                counts[path] = 0
    return counts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Douban crawlers")
    parser.add_argument("--pages", type=int, default=1, help="Top250 pages to crawl")
    parser.add_argument("--comment-limit", type=int, default=5, help="Comments per movie")
    parser.add_argument("--no-details", action="store_true", help="Skip detail pages")
    parser.add_argument("--no-images", action="store_true", default=True, help="Skip images")
    parser.add_argument("--requests-only", action="store_true", help="Only run requests version")
    parser.add_argument("--scrapy-only", action="store_true", help="Only run Scrapy version")
    args = parser.parse_args()

    print("=" * 60)
    print("Douban Crawler Benchmark: Scrapy vs Requests")
    print("=" * 60)
    print(f"  Top250 pages      : {args.pages}")
    print(f"  Comment limit     : {args.comment_limit}")
    print(f"  Crawl details     : {not args.no_details}")
    print(f"  Download images   : {not args.no_images}")
    print()

    results: list[dict[str, Any]] = []

    if not args.scrapy_only:
        print(">>> Running requests-based crawler ...")
        try:
            r = _run_requests_crawler(
                pages=args.pages,
                comment_limit=args.comment_limit,
                no_details=args.no_details,
                no_images=args.no_images,
            )
            results.append(r)
            print(r["stdout"])
            if r["stderr"]:
                print("  [requests stderr]", r["stderr"][:500])
        except Exception as e:
            print(f"  [ERROR] requests crawler failed: {e}")
        print()

    if not args.requests_only:
        print(">>> Running Scrapy-based crawler ...")
        try:
            r = _run_scrapy_crawler(
                pages=args.pages,
                comment_limit=args.comment_limit,
                no_details=args.no_details,
                no_images=args.no_images,
            )
            results.append(r)
            # Print last 20 lines of stdout
            lines = r["stdout"].splitlines()
            print("\n".join(lines[-20:]) if len(lines) > 20 else r["stdout"])
            if r["stderr"]:
                print("  [scrapy stderr]", r["stderr"][:500])
        except Exception as e:
            print(f"  [ERROR] Scrapy crawler failed: {e}")
        print()

    # -----------------------------------------------------------------------
    # Performance comparison table
    # -----------------------------------------------------------------------
    if results:
        print("-" * 60)
        print("Performance Comparison")
        print("-" * 60)

        if tabulate:
            headers = ["Engine", "Items", "Elapsed", "Avg/Item"]
            table = [
                [r["engine"], r["items"], r["elapsed_str"], r["avg_str"]]
                for r in results
            ]
            print(tabulate.tabulate(table, headers=headers, tablefmt="grid"))
        else:
            for r in results:
                print(
                    f"  {r['engine']:12s} | items={r['items']:4d} | "
                    f"elapsed={r['elapsed_str']:>8s} | avg={r['avg_str']:>8s}"
                )
        print()

    # -----------------------------------------------------------------------
    # Code complexity comparison
    # -----------------------------------------------------------------------
    print("-" * 60)
    print("Code Complexity (source lines of code)")
    print("-" * 60)

    requests_files = [
        "requests_douban/__init__.py",
        "requests_douban/anti_spider.py",
        "requests_douban/cleaner.py",
        "requests_douban/cli.py",
        "requests_douban/config.py",
        "requests_douban/crawler.py",
        "requests_douban/http_client.py",
        "requests_douban/image_downloader.py",
        "requests_douban/parser.py",
        "requests_douban/selenium_renderer.py",
    ]

    scrapy_files = [
        "scrapy_douban/scrapy_douban/__init__.py",
        "scrapy_douban/scrapy_douban/items.py",
        "scrapy_douban/scrapy_douban/settings.py",
        "scrapy_douban/scrapy_douban/middlewares.py",
        "scrapy_douban/scrapy_douban/pipelines.py",
        "scrapy_douban/scrapy_douban/spiders/__init__.py",
        "scrapy_douban/scrapy_douban/spiders/top250.py",
        "scrapy_douban/scrapy_douban/spiders/custom.py",
    ]

    req_counts = _count_lines(requests_files)
    scr_counts = _count_lines(scrapy_files)

    print(f"  {'Module':50s} {'Lines':>8s}")
    print(f"  {'-'*50} {'-'*8}")
    req_total = 0
    for path, count in req_counts.items():
        print(f"  {path:50s} {count:>8d}")
        req_total += count
    print(f"  {'-'*50} {'-'*8}")
    print(f"  {'Requests total':50s} {req_total:>8d}")
    print()

    for path, count in scr_counts.items():
        print(f"  {path:50s} {count:>8d}")
    scr_total = sum(scr_counts.values())
    print(f"  {'-'*50} {'-'*8}")
    print(f"  {'Scrapy total':50s} {scr_total:>8d}")
    print()

    # (reused parser & cleaner shared with requests version)
    reused = _count_lines(["requests_douban/parser.py", "requests_douban/cleaner.py"])
    reused_total = sum(reused.values())
    print(f"  (Note: Scrapy reuses parser.py + cleaner.py = {reused_total} lines from requests)")
    print(f"   Scrapy exclusive code = {scr_total - reused_total} lines")
    print()

    # -----------------------------------------------------------------------
    # Architecture comparison chart
    # -----------------------------------------------------------------------
    print("-" * 60)
    print("Architecture Comparison")
    print("-" * 60)
    print("""
  Requests version (requests_douban):
    DoubanCrawler (crawler.py) ─► DoubanHttpClient (http_client.py)
         │                              ├─ requests.Session + retry
         ├─ crawl_urls()                 ├─ anti_spider detection
         ├─ crawl_movie_top250()         └─ proxy / UA rotation
         ├─ crawl_details() ───► SeleniumRenderer (selenium_renderer.py)
         ├─ download_images() ──► image_downloader.py
         └─ save_items() ───► JSON / CSV / MySQL
    Data flow: sequential / ThreadPoolExecutor → manual orchestration

  Scrapy version (scrapy_douban):
    Top250Spider (spiders/top250.py)
         ├─ start_requests() ──► Downloader
         ├─ parse_list()       ──► AntiSpiderRetryMiddleware
         ├─ parse_detail()     ──► RandomUserAgentMiddleware
         └─ parse_comments()   ──► ProxyMiddleware
    Pipelines:
         ├─ CleaningPipeline (reuses cleaner.py)
         ├─ ImageDownloadPipeline (reuses image_downloader.py)
         └─ ExportPipeline (JSON + CSV)
    Data flow: async event-driven → Scrapy Engine orchestrates everything
""")

    print("=" * 60)
    print("Done. Remember to clean up test data:")
    print(f"  rm -rf data/bench_requests data/bench_scrapy")
    print("=" * 60)


if __name__ == "__main__":
    main()
