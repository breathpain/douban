"""scrapy_douban 项目 Scrapy 配置。

镜像 requests_douban.config 中 CrawlConfig 的默认值，
同时添加 Scrapy 特有的礼貌爬取/反爬虫行为调优。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保项目根目录 (F:\douban) 在 sys.path 中，
# 使 ``scrapy crawl`` 从 ``scrapy_douban/`` 目录运行时，``requests_douban`` 可被导入。
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# ---------------------------------------------------------------------------
# 核心配置
# ---------------------------------------------------------------------------
BOT_NAME = "scrapy_douban"
SPIDER_MODULES = ["scrapy_douban.spiders"]
NEWSPIDER_MODULE = "scrapy_douban.spiders"
ROBOTSTXT_OBEY = False
COOKIES_ENABLED = True

# ---------------------------------------------------------------------------
# 并发与延迟（镜像 CrawlConfig: delay_min=1.2, delay_max=3.5）
# ---------------------------------------------------------------------------
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 4
# DOWNLOAD_DELAY = 2.35 + RANDOMIZE_DOWNLOAD_DELAY 产生 uniform(1.175, 3.525) 的延迟
DOWNLOAD_DELAY = 2.35
RANDOMIZE_DOWNLOAD_DELAY = True

# ---------------------------------------------------------------------------
# 重试（镜像 CrawlConfig.retry_times = 3）
# ---------------------------------------------------------------------------
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [403, 408, 418, 429, 500, 502, 503, 504]

# ---------------------------------------------------------------------------
# 超时（镜像 CrawlConfig.request_timeout = 15）
# ---------------------------------------------------------------------------
DOWNLOAD_TIMEOUT = 15

# ---------------------------------------------------------------------------
# User-Agent 轮换
# ---------------------------------------------------------------------------
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# 代理（通过命令行或环境变量设置；默认禁用）
# ---------------------------------------------------------------------------
# PROXY = "http://127.0.0.1:7890"          # 示例
# PROXY_POOL = (...)                        # 代理字典元组

# ---------------------------------------------------------------------------
# 供中间件/管道/爬虫使用的自定义设置
# ---------------------------------------------------------------------------
MAX_PAGES = 10                            # 爬取页数（top250 = 10 页）
DOWNLOAD_IMAGES = True                    # 切换图片管道开关
COMMENT_LIMIT = 20                        # 每部电影默认短评条数
CRAWL_DETAILS = True                      # 是否获取电影详情
DOUBAN_COOKIE = (
    "bid=6hFFPciD6uQ; ll=118254; viewed=3031572; ct=y; "
    "dbsawcv1=MTc3ODIzNDEwN0A3OGM5NTJhMmNjM2RmN2ZjNjZjZGNiZmYzNjc1MzAxZjNjMTU1YjRjZDBjODlmMGUxMzFlZjliNmQ0ZmMxNzY1QGIzOTc3MDFhM2RjMTY2OWRAZjk5YzM5NGNkM2Iw; "
    "ap_v=0,6.0"
)                                      # 豆瓣登录 Cookie 字符串
RANDOM_UA_STRICT = False                  # 始终使用全新的 UA

# ---------------------------------------------------------------------------
# 中间件顺序（数字越小 = 越早/越靠近引擎）
# ---------------------------------------------------------------------------
DOWNLOADER_MIDDLEWARES: dict[str, int] = {
    # 禁用内置 UA（我们自行轮换）
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    # 自定义中间件置于内置重试之前，使反爬检测优先触发
    "scrapy_douban.middlewares.RandomUserAgentMiddleware": 400,
    "scrapy_douban.middlewares.ProxyMiddleware": 450,
    "scrapy_douban.middlewares.DoubanCookieMiddleware": 480,
    "scrapy_douban.middlewares.AntiSpiderRetryMiddleware": 525,
    # 内置重试（处理标准 HTTP 状态码）
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": 530,
    # 内置延迟（per-slot，非阻塞）替代 RandomDelayMiddleware
    "scrapy.downloadermiddlewares.downloadtimeout.DownloadTimeoutMiddleware": 350,
}

# ---------------------------------------------------------------------------
# 管道顺序
# ---------------------------------------------------------------------------
ITEM_PIPELINES: dict[str, int] = {
    "scrapy_douban.pipelines.CleaningPipeline": 200,
    "scrapy_douban.pipelines.ImageDownloadPipeline": 300,
    "scrapy_douban.pipelines.ExportPipeline": 400,
}

# ---------------------------------------------------------------------------
# Feed 导出（保持 JSON 和 CSV 与 requests 版本同步）
# ---------------------------------------------------------------------------
FEED_STORAGES_BASE: dict[str, str] = {}
FEED_EXPORTERS_BASE: dict[str, str] = {}
FEED_EXPORT_ENCODING = "utf-8"

# ---------------------------------------------------------------------------
# 扩展
# ---------------------------------------------------------------------------
TELNETCONSOLE_ENABLED = False

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
LOG_LEVEL = "INFO"
