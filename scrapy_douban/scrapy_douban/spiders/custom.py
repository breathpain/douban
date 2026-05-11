"""Scrapy spider that works with arbitrary Douban list/search URLs.

Supports the same URL-expansion logic as the requests version
(``expand_paginated_urls``) so that a single URL can span multiple pages.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import scrapy
from scrapy.http import Response

from member_a_douban.parser import (
    DoubanItem as ParserItem,
    enrich_movie_detail,
    has_movie_detail_info,
    has_next_page,
    parse_douban_items,
    parse_movie_comments,
)

from ..items import DoubanItem as ScrapyItem
from .top250 import (  # reuse helpers from top250 spider
    _deduplicate_comments,
    _mobile_subject_url,
    _parser_to_scrapy,
)


class CustomUrlsSpider(scrapy.Spider):
    """Crawl user-supplied Douban list URLs.

    Example::

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

        # Parse comma / newline separated URLs
        raw_urls = [u.strip() for u in urls.split(",") if u.strip()]
        self.start_urls_raw = raw_urls

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        kwargs.setdefault("max_pages", crawler.settings.get("MAX_PAGES", "1"))
        kwargs.setdefault("comment_limit", str(crawler.settings.getint("COMMENT_LIMIT", 20)))
        kwargs.setdefault("crawl_details", str(crawler.settings.getbool("CRAWL_DETAILS", True)))
        return super().from_crawler(crawler, *args, **kwargs)

    # ----------------------------------------------------------------
    # 1. Build expanded URL list and start requests
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
    # 2. Parse list page
    # ----------------------------------------------------------------

    def parse_list(self, response: Response):
        parser_items = parse_douban_items(response.text, response.url)
        for p_item in parser_items:
            scrapy_item = _parser_to_scrapy(p_item)
            yield scrapy_item

    # ----------------------------------------------------------------
    # URL expansion
    # ----------------------------------------------------------------

    def _expand_url(self, url: str) -> list[str]:
        """Expand a single URL into multiple paginated URLs."""
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
