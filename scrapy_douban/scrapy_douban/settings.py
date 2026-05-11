"""Scrapy settings for scrapy_douban project.

Mirrors the CrawlConfig defaults from member_a_douban.config while adding
Scrapy-specific tuning for polite / anti-spider behaviour.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root (F:\douban) is on sys.path so ``member_a_douban`` is importable
# when ``scrapy crawl`` is run from the ``scrapy_douban/`` directory.
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
BOT_NAME = "scrapy_douban"
SPIDER_MODULES = ["scrapy_douban.spiders"]
NEWSPIDER_MODULE = "scrapy_douban.spiders"
ROBOTSTXT_OBEY = False
COOKIES_ENABLED = True

# ---------------------------------------------------------------------------
# Concurrency & delay  (mirrors CrawlConfig: delay_min=1.2, delay_max=3.5)
# ---------------------------------------------------------------------------
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 4
# DOWNLOAD_DELAY = 2.35 + RANDOMIZE_DOWNLOAD_DELAY gives uniform(1.175, 3.525)
DOWNLOAD_DELAY = 2.35
RANDOMIZE_DOWNLOAD_DELAY = True

# ---------------------------------------------------------------------------
# Retry  (mirrors CrawlConfig.retry_times = 3)
# ---------------------------------------------------------------------------
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [403, 408, 418, 429, 500, 502, 503, 504]

# ---------------------------------------------------------------------------
# Timeout  (mirrors CrawlConfig.request_timeout = 15)
# ---------------------------------------------------------------------------
DOWNLOAD_TIMEOUT = 15

# ---------------------------------------------------------------------------
# User-Agent rotation
# ---------------------------------------------------------------------------
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Proxy (set via command-line or environment; disabled by default)
# ---------------------------------------------------------------------------
# PROXY = "http://127.0.0.1:7890"          # example
# PROXY_POOL = (...)                        # tuple of proxy dicts

# ---------------------------------------------------------------------------
# Custom settings consumed by middlewares / pipelines / spiders
# ---------------------------------------------------------------------------
MAX_PAGES = 10                            # pages to crawl (top250 = 10 pages)
DOWNLOAD_IMAGES = True                    # toggle image pipeline
COMMENT_LIMIT = 20                        # default comments per movie
CRAWL_DETAILS = True                      # fetch movie details
DOUBAN_COOKIE = (
    "bid=6hFFPciD6uQ; ll=118254; viewed=3031572; ct=y; "
    "dbsawcv1=MTc3ODIzNDEwN0A3OGM5NTJhMmNjM2RmN2ZjNjZjZGNiZmYzNjc1MzAxZjNjMTU1YjRjZDBjODlmMGUxMzFlZjliNmQ0ZmMxNzY1QGIzOTc3MDFhM2RjMTY2OWRAZjk5YzM5NGNkM2Iw; "
    "ap_v=0,6.0"
)                                      # Douban login cookie string
RANDOM_UA_STRICT = False                  # always use a fresh UA

# ---------------------------------------------------------------------------
# Middleware ordering  (lower = earlier / closer to engine)
# ---------------------------------------------------------------------------
DOWNLOADER_MIDDLEWARES: dict[str, int] = {
    # Disable built-in UA (we rotate ourselves)
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    # Custom precede built-in retry so anti-spider detection fires first
    "scrapy_douban.middlewares.RandomUserAgentMiddleware": 400,
    "scrapy_douban.middlewares.ProxyMiddleware": 450,
    "scrapy_douban.middlewares.DoubanCookieMiddleware": 480,
    "scrapy_douban.middlewares.AntiSpiderRetryMiddleware": 525,
    # Built-in retry (handles standard HTTP codes)
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": 530,
    # Built-in delay (per-slot, non-blocking) replaces RandomDelayMiddleware
    "scrapy.downloadermiddlewares.downloadtimeout.DownloadTimeoutMiddleware": 350,
}

# ---------------------------------------------------------------------------
# Pipeline ordering
# ---------------------------------------------------------------------------
ITEM_PIPELINES: dict[str, int] = {
    "scrapy_douban.pipelines.CleaningPipeline": 200,
    "scrapy_douban.pipelines.ImageDownloadPipeline": 300,
    "scrapy_douban.pipelines.ExportPipeline": 400,
}

# ---------------------------------------------------------------------------
# Feed export (keep JSON & CSV syncable with requests version)
# ---------------------------------------------------------------------------
FEED_STORAGES_BASE: dict[str, str] = {}
FEED_EXPORTERS_BASE: dict[str, str] = {}
FEED_EXPORT_ENCODING = "utf-8"

# ---------------------------------------------------------------------------
# Extension
# ---------------------------------------------------------------------------
TELNETCONSOLE_ENABLED = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = "INFO"
