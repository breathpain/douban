"""支持任意豆瓣列表/搜索 URL 的 Scrapy 爬虫。

支持与 requests 版本相同的 URL 展开逻辑（``expand_paginated_urls``），
使单个 URL 可扩展为多个分页。
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import scrapy
from scrapy.http import Response

from requests_douban.parser import (
    DoubanItem as ParserItem,
    enrich_movie_detail,
    has_movie_detail_info,
    has_next_page,
    parse_douban_items,
    parse_movie_comments,
)

from ..items import DoubanItem as ScrapyItem
from .top250 import (  # 复用 top250 爬虫的辅助函数
    _deduplicate_comments,
    _mobile_subject_url,
    _parser_to_scrapy,
)


class CustomUrlsSpider(scrapy.Spider):
    """爬取用户提供的豆瓣列表 URL。

    示例::

        scrapy crawl custom -a urls="https://movie.douban.com/top250?start=0"
    """

    name = "custom"

    def __init__(
        self,
        urls: str = "",
        max_pages: str = "1",
        comment_limit: str = "20",
        crawl_details: str = "true",
        page_param: str = "start",
        page_size: str = "25",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.max_pages = int(max_pages)
        self.comment_limit = int(comment_limit)
        self.crawl_details = crawl_details.lower() in ("true", "1", "yes")
        self.page_param = page_param
        self.page_size = int(page_size)

        # 解析逗号/换行符分隔的 URL
        raw_urls = [u.strip() for u in urls.split(",") if u.strip()]
        self.start_urls_raw = raw_urls

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        kwargs.setdefault("max_pages", crawler.settings.get("MAX_PAGES", "1"))
        kwargs.setdefault("comment_limit", str(crawler.settings.getint("COMMENT_LIMIT", 20)))
        kwargs.setdefault("crawl_details", str(crawler.settings.getbool("CRAWL_DETAILS", True)))
        return super().from_crawler(crawler, *args, **kwargs)

    # ----------------------------------------------------------------
    # 1. 构建展开的 URL 列表并启动请求
    # ----------------------------------------------------------------

    async def start_requests(self):
        for raw_url in self.start_urls_raw:
            for url in self._expand_url(raw_url):
                yield scrapy.Request(
                    url,
                    callback=self.parse_list,
                    headers={"Referer": "https://www.douban.com/"},
                )

    # ----------------------------------------------------------------
    # 2. 解析列表页
    # ----------------------------------------------------------------

    def parse_list(self, response: Response):
        parser_items = parse_douban_items(response.text, response.url)
        for p_item in parser_items:
            scrapy_item = _parser_to_scrapy(p_item)
            yield scrapy_item

    # ----------------------------------------------------------------
    # URL 展开
    # ----------------------------------------------------------------

    def _expand_url(self, url: str) -> list[str]:
        """将单个 URL 展开为多个分页 URL。"""
        if self.max_pages <= 1:
            return [url]

        if "{page}" in url or "{start}" in url:
            return [
                url.format(page=page + 1, start=page * self.page_size)
                for page in range(self.max_pages)
            ]

        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        param_found = self.page_param if self.page_param in query else (
            "start" if "start" in query else ("page" if "page" in query else None)
        )
        if param_found is None:
            return [url]

        first_value = int(query.get(param_found, "0") or 0)
        urls = []
        for page in range(self.max_pages):
            if param_found == "start":
                query[param_found] = str(first_value + page * self.page_size)
            else:
                query[param_found] = str(first_value + page)
            urls.append(urlunsplit(parts._replace(query=urlencode(query))))
        return urls
