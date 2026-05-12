"""豆瓣电影 Top250 的 Scrapy 爬虫。

工作流程
--------
1. 通过 Scrapy 请求 Top250 列表页
2. 通过 ``requests_douban.parser`` 解析列表条目
3. 通过 ``requests_douban.crawler.DoubanCrawler`` 丰富电影数据和短评
   （内部处理 Desktop→Mobile→Selenium 回退逻辑）
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlencode

import scrapy
from scrapy.http import Response

from requests_douban.config import CrawlConfig
from requests_douban.crawler import DoubanCrawler
from requests_douban.http_client import DoubanHttpClient
from requests_douban.parser import (
    DoubanItem as ParserItem,
    enrich_movie_detail,
    has_movie_detail_info,
    parse_douban_items,
)
from requests_douban.selenium_renderer import SeleniumRenderer

from ..items import DoubanItem as ScrapyItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 爬虫
# ---------------------------------------------------------------------------

class Top250Spider(scrapy.Spider):
    """爬取豆瓣电影 Top250 列表页、详情页和短评。

    列表页通过 Scrapy 获取（速度快）。
    详情 + 短评丰富化委托给 ``requests_douban`` 的
    ``DoubanCrawler._crawl_detail_item`` 逻辑，在 HTTP 客户端
    被封锁时回退到 Selenium。
    """

    name = "top250"

    def __init__(
        self,
        max_pages: str = "10",
        comment_limit: str = "20",
        crawl_details: str = "true",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.max_pages = int(max_pages)
        self.comment_limit = int(comment_limit)
        self.crawl_details = crawl_details.lower() in ("true", "1", "yes")
        self.http_client: DoubanHttpClient | None = None
        self._renderer: SeleniumRenderer | None = None

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        kwargs.setdefault("max_pages", crawler.settings.get("MAX_PAGES", "10"))
        kwargs.setdefault("comment_limit", str(crawler.settings.getint("COMMENT_LIMIT", 20)))
        kwargs.setdefault("crawl_details", str(crawler.settings.getbool("CRAWL_DETAILS", True)))
        spider = super().from_crawler(crawler, *args, **kwargs)

        # 从 Scrapy settings 构建 CrawlConfig 以供 requests_douban 回退使用
        cfg = CrawlConfig(
            request_timeout=crawler.settings.getint("DOWNLOAD_TIMEOUT", 15),
            retry_times=crawler.settings.getint("RETRY_TIMES", 3),
            delay_min=1.2,
            delay_max=3.5,
            cookie=crawler.settings.get("DOUBAN_COOKIE"),
            proxies=None,
            proxy_pool=(),
            chrome_driver_path=str(Path(__file__).resolve().parent.parent.parent.parent / "chromedriver.exe"),
            use_selenium=True,
            selenium_headless=True,
            comment_limit=crawler.settings.getint("COMMENT_LIMIT", 20),
            user_agents=(
                crawler.settings.get("USER_AGENT",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"),
            ),
        )
        spider.http_client = DoubanHttpClient(cfg)
        spider._cfg = cfg
        spider._douban_crawler = DoubanCrawler(cfg)
        return spider

    # ----------------------------------------------------------------
    # 1. 启动：Top250 列表页
    # ----------------------------------------------------------------

    async def start(self):
        for page in range(self.max_pages):
            url = "https://movie.douban.com/top250?" + urlencode({"start": page * 25})
            yield scrapy.Request(
                url,
                callback=self.parse_list,
                headers={"Referer": "https://www.douban.com/"},
            )

    # ----------------------------------------------------------------
    # 2. 解析列表页 → 通过 requests_douban 管道丰富详情
    # ----------------------------------------------------------------

    def parse_list(self, response: Response):
        parser_items = parse_douban_items(response.text, response.url)

        if not self.crawl_details:
            for p_item in parser_items:
                yield _parser_to_scrapy(p_item)
            return

        # 为所有详情页打开 Selenium 渲染器一次（如需要）
        renderer: SeleniumRenderer | None = None
        try:
            renderer = SeleniumRenderer(self._cfg).__enter__()
        except Exception as exc:
            logger.warning("Selenium not available, will only use HTTP client: %s", exc)

        for p_item in parser_items:
            try:
                self._enrich_via_member_a(p_item, renderer)
            except Exception as exc:
                p_item.detail_error = str(exc)
            yield _parser_to_scrapy(p_item)

        if renderer:
            try:
                renderer.__exit__(None, None, None)
            except Exception:
                pass

    def _enrich_via_member_a(
        self,
        item: ParserItem,
        renderer: SeleniumRenderer | None,
    ) -> None:
        """为单个 ParserItem 丰富详情和短评数据。

        镜像 ``requests_douban.crawler.DoubanCrawler._crawl_detail_item`` 逻辑。
        """
        if not item.url:
            return

        # ---- 详情页 HTML ----
        html = self._fetch_detail_html(item.url, item.source_page, renderer)
        if not html:
            item.detail_error = "failed to fetch detail page via all methods"
            return

        enrich_movie_detail(item, html)

        # ---- 短评（通过 DoubanCrawler，逻辑与 requests_douban 相同）----
        if self.comment_limit > 0:
            self._douban_crawler._crawl_comments(item, html, renderer)

    def _fetch_detail_html(
        self,
        url: str,
        source_page: str,
        renderer: SeleniumRenderer | None,
    ) -> str | None:
        """先尝试 HTTP 客户端，再尝试移动端 URL，最后 Selenium。"""
        # 桌面端通过 HTTP 客户端
        try:
            result = self.http_client.get(url, referer=source_page)
            if has_movie_detail_info(result.text):
                return result.text
        except Exception as exc:
            desktop_err = exc
        else:
            desktop_err = RuntimeError("desktop detail page has no parseable detail info")

        # 移动端通过 HTTP 客户端
        mobile_url = _mobile_subject_url(url)
        if mobile_url:
            try:
                result = self.http_client.get(mobile_url, referer=url)
                if has_movie_detail_info(result.text):
                    return result.text
            except Exception as mobile_exc:
                mobile_err = mobile_exc
            else:
                mobile_err = RuntimeError("mobile detail page has no parseable detail info")

        # Selenium 回退
        if renderer is not None:
            try:
                result = renderer.render(url)
                if has_movie_detail_info(result.text):
                    logger.info("Selenium fallback OK: %s", url)
                    return result.text
            except Exception as sel_exc:
                logger.warning(
                    "Selenium also failed for %s: %s; desktop_err=%s; mobile_err=%s",
                    url, sel_exc, desktop_err, mobile_err,
                )
        else:
            logger.warning(
                "Selenium not available for %s; desktop_err=%s; mobile_err=%s",
                url, desktop_err, mobile_err,
            )
        return None


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _parser_to_scrapy(p: ParserItem) -> ScrapyItem:
    d = asdict(p)
    item = ScrapyItem()
    for k, v in d.items():
        item[k] = v
    return item


def _mobile_subject_url(url: str) -> str:
    match = re.search(r"/subject/(\d+)/?", url)
    if not match:
        return ""
    return f"https://m.douban.com/movie/subject/{match.group(1)}/"


def _deduplicate_comments(existing: list[str], incoming: list[str]) -> list[str]:
    """合并两份评论列表，按评论文本去重。"""
    seen: set[str] = set()
    result: list[str] = []
    for comment in existing + incoming:
        key = _comment_key(comment)
        if key and key not in seen:
            seen.add(key)
            result.append(comment)
    return result


def _comment_key(comment: str) -> str:
    """从格式化评论字符串中提取去重 key（评论文本）。"""
    match = re.search(r"评论：(.*)", comment)
    if match:
        text = match.group(1).strip()
        return text.rstrip("。.!！")
    return comment.strip()


