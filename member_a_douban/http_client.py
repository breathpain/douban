"""Requests-based client with retry, delay, cookies, and rotating headers."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Final

try:
    import requests
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise ModuleNotFoundError(
        "requests is required. Install dependencies with: pip install -r requirements.txt"
    ) from exc

from .anti_spider import (
    BLOCK_TITLE_PATTERNS,
    choose_proxy,
    choose_user_agent,
    is_blocked,
    parse_cookie,
    polite_sleep,
)
from .config import CrawlConfig


DOUBAN_REFERER: Final = "https://www.douban.com/"


class BlockedByDoubanError(RuntimeError):
    """Raised when Douban returns an obvious anti-spider page."""


_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _extract_title(html: str) -> str:
    """Extract the <title> text from HTML."""
    match = _TITLE_RE.search(html)
    return match.group(1).strip() if match else ""


@dataclass
class HttpResult:
    url: str
    status_code: int
    text: str
    used_selenium: bool = False


class DoubanHttpClient:
    def __init__(self, config: CrawlConfig) -> None:
        self.config = config
        self.session = requests.Session()
        if config.proxies is None:
            self.session.trust_env = False
        self.session.cookies.update(parse_cookie(config.cookie))

    def get(self, url: str, referer: str | None = None) -> HttpResult:
        last_error: Exception | None = None

        for attempt in range(1, self.config.retry_times + 1):
            headers = self._headers(referer)
            proxies = choose_proxy(self.config.proxies, self.config.proxy_pool)
            try:
                polite_sleep(self.config.delay_min, self.config.delay_max)
                response = self.session.get(
                    url,
                    headers=headers,
                    proxies=proxies,
                    timeout=self.config.request_timeout,
                )
                if "douban.com" in response.url:
                    response.encoding = "utf-8"
                elif not response.encoding or response.encoding.lower() == "iso-8859-1":
                    response.encoding = response.apparent_encoding or "utf-8"
                text = response.text
                if "sec.douban.com" in response.url:
                    raise BlockedByDoubanError(
                        f"redirected to Douban security check, final_url={response.url}"
                    )
                if is_blocked(response.status_code, text, response.headers):
                    raise BlockedByDoubanError(
                        f"blocked by Douban, status={response.status_code}, url={url}"
                    )
                # Check page title for anti-spider / error pages
                title = _extract_title(text)
                if title and any(p in title for p in BLOCK_TITLE_PATTERNS):
                    raise BlockedByDoubanError(
                        f"blocked by Douban, suspicious title={title!r}, url={url}"
                    )
                # Detect redirects to login / security pages
                original_path = url.split("?")[0].rstrip("/")
                final_path = response.url.split("?")[0].rstrip("/")
                if (
                    "douban.com" in response.url
                    and original_path != final_path
                    and "accounts.douban.com" in response.url
                ):
                    raise BlockedByDoubanError(
                        f"redirected to login page, from={original_path} to={final_path}"
                    )
                response.raise_for_status()
                return HttpResult(url=response.url, status_code=response.status_code, text=text)
            except (requests.RequestException, BlockedByDoubanError) as exc:
                last_error = exc
                if attempt < self.config.retry_times:
                    polite_sleep(self.config.delay_min, self.config.delay_max)

        raise RuntimeError(f"failed to fetch {url}: {last_error}") from last_error

    def _headers(self, referer: str | None = None) -> dict[str, str]:
        accept_languages = (
            "zh-CN,zh;q=0.9,en;q=0.8",
            "zh-CN,zh;q=0.9",
            "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        )
        user_agent = choose_user_agent(self.config.user_agents)
        headers = {
            "User-Agent": user_agent,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": random.choice(accept_languages),
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin" if referer else "none",
            "Sec-Fetch-User": "?1",
            "Referer": referer or DOUBAN_REFERER,
        }
        if "Chrome/" in user_agent:
            headers.update(
                {
                    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                }
            )
        return headers
