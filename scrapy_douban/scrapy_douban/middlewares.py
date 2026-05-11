"""Downloader middlewares for the Douban Scrapy crawler.

Provides:
- ``RandomUserAgentMiddleware`` – rotate User-Agent per request
- ``ProxyMiddleware`` – apply proxy settings
- ``AntiSpiderRetryMiddleware`` – detect anti-spider blocks and retry
- ``RandomDelayMiddleware`` – fine-grained delay control
"""

from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING

from scrapy import Request, signals
from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy.exceptions import IgnoreRequest, NotConfigured

try:
    from member_a_douban.anti_spider import (
        BLOCK_TITLE_PATTERNS,
        choose_user_agent,
        is_blocked,
        parse_cookie,
    )
    from member_a_douban.config import CrawlConfig, DEFAULT_USER_AGENTS
    from member_a_douban.http_client import _extract_title
except ImportError:
    # Fallback definitions when member_a_douban is not importable
    CrawlConfig = None  # type: ignore[assignment]
    DEFAULT_USER_AGENTS = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )

    def choose_user_agent(user_agents: tuple[str, ...]) -> str:
        return random.choice(user_agents)

    def is_blocked(status_code: int, html: str, headers=None) -> bool:  # type: ignore[no-untyped-def]
        return status_code in (403, 418, 429)

    def _extract_title(html: str) -> str:
        import re
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else ""

    BLOCK_TITLE_PATTERNS = ()

    def parse_cookie(cookie: str | None) -> dict[str, str]:
        if not cookie:
            return {}
        result: dict[str, str] = {}
        for part in cookie.split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                result[k.strip()] = v.strip()
        return result


# ---------------------------------------------------------------------------
# 1. Random User-Agent Middleware
# ---------------------------------------------------------------------------

class RandomUserAgentMiddleware:
    """Rotate User-Agent from a configurable tuple."""

    def __init__(self, user_agents: tuple[str, ...]) -> None:
        self.user_agents = user_agents

    @classmethod
    def from_crawler(cls, crawler) -> RandomUserAgentMiddleware:
        ua_tuple: tuple[str, ...] = tuple(
            crawler.settings.getlist("USER_AGENT_LIST")
        ) or getattr(DEFAULT_USER_AGENTS, "_fields", DEFAULT_USER_AGENTS)

        # Fall back to DEFAULT_USER_AGENTS if settings provide nothing
        if not ua_tuple:
            ua_tuple = DEFAULT_USER_AGENTS
        return cls(ua_tuple)

    def process_request(self, request: Request, spider) -> Request | None:
        request.headers["User-Agent"] = choose_user_agent(self.user_agents)
        return None


# ---------------------------------------------------------------------------
# 2. Proxy Middleware
# ---------------------------------------------------------------------------

class ProxyMiddleware:
    """Apply a proxy to each request when configured via settings."""

    def __init__(self, proxies: tuple[dict[str, str], ...] | None = None) -> None:
        self.proxies = proxies or ()

    @classmethod
    def from_crawler(cls, crawler) -> ProxyMiddleware:
        from member_a_douban.config import CrawlConfig
        # Try reading from CrawlConfig (when run via app.py)
        if CrawlConfig is not None:
            try:
                member_a_config: CrawlConfig = getattr(crawler, "member_a_config", None)  # type: ignore[union-attr]
                if member_a_config and member_a_config.proxy_pool:
                    return cls(member_a_config.proxy_pool)
                if member_a_config and member_a_config.proxies:
                    return cls((member_a_config.proxies,))
            except Exception:
                pass

        # Fallback to settings
        single = crawler.settings.get("PROXY")
        pool = crawler.settings.get("PROXY_POOL")

        if single:
            proxies = ({"http": single, "https": single},)
        elif pool:
            proxies = tuple(pool)
        else:
            proxies = ()

        if not proxies:
            raise NotConfigured("No proxy configured")
        return cls(proxies)

    def process_request(self, request: Request, spider) -> None:
        if self.proxies:
            proxy = random.choice(self.proxies)
            request.meta["proxy"] = proxy.get("http", "") or proxy.get("https", "")


# ---------------------------------------------------------------------------
# 3. Anti-Spider Retry Middleware
# ---------------------------------------------------------------------------

class AntiSpiderRetryMiddleware(RetryMiddleware):
    """Extend built-in RetryMiddleware to detect Douban anti-spider pages.

    Checks 200 OK responses for blocked-page patterns (title, keywords)
    and retries them as if they were error responses.
    """

    def process_response(self, request: Request, response, spider):
        if response.status == 200:
            html = response.text

            # Convert Scrapy Headers (bytes values) to str for is_blocked
            str_headers: dict[str, str] = {}
            for k, v in response.headers.items():
                key = k.decode("utf-8", errors="replace").lower()
                # Scrapy Headers stores values as list[bytes]
                if isinstance(v, (list, tuple)):
                    str_headers[key] = v[0].decode("utf-8", errors="replace") if v else ""
                else:
                    str_headers[key] = v.decode("utf-8", errors="replace")

            # Check via is_blocked (status + keywords)
            if is_blocked(response.status, html, str_headers):
                reason = "Anti-spider block (content keywords)"
                return self._retry(request, reason, spider) or response

            # Check <title> patterns
            title = _extract_title(html)
            if title and any(p in title for p in BLOCK_TITLE_PATTERNS):
                reason = f"Anti-spider block (title={title[:40]})"
                return self._retry(request, reason, spider) or response

        return super().process_response(request, response, spider)


# ---------------------------------------------------------------------------
# 4. Random Delay Middleware
# ---------------------------------------------------------------------------

class RandomDelayMiddleware:
    """Ensure a random delay before each request.

    Unlike Scrapy's built-in DOWNLOAD_DELAY (which is per-slot and fixed),
    this applies a per-request random delay within [min, max] seconds.
    """

    def __init__(self, delay_min: float, delay_max: float) -> None:
        self.delay_min = delay_min
        self.delay_max = delay_max

    @classmethod
    def from_crawler(cls, crawler) -> RandomDelayMiddleware:
        delay_min = crawler.settings.getfloat("RANDOM_DELAY_MIN", 1.2)
        delay_max = crawler.settings.getfloat("RANDOM_DELAY_MAX", 3.5)
        return cls(delay_min, delay_max)

    def process_request(self, request: Request, spider) -> None:
        delay = random.uniform(self.delay_min, self.delay_max)
        time.sleep(delay)


# ---------------------------------------------------------------------------
# 5. Cookie Middleware (apply Douban cookies if provided)
# ---------------------------------------------------------------------------

class DoubanCookieMiddleware:
    """Inject Douban cookies into every request."""

    cookie_dict: dict[str, str] = {}

    def __init__(self, cookie_string: str | None) -> None:
        if cookie_string:
            self.cookie_dict = parse_cookie(cookie_string)

    @classmethod
    def from_crawler(cls, crawler) -> DoubanCookieMiddleware:
        cookie = crawler.settings.get("DOUBAN_COOKIE")
        return cls(cookie)

    def process_request(self, request: Request, spider) -> None:
        if self.cookie_dict:
            # Build Cookie header directly (stronger than request.cookies update)
            cookie_str = "; ".join(f"{k}={v}" for k, v in self.cookie_dict.items())
            request.headers["Cookie"] = cookie_str
            # Prevent CookiesMiddleware from overwriting our Cookie header
            request.meta["dont_merge_cookies"] = True
            # Also keep request.cookies as fallback
            request.cookies.update(self.cookie_dict)
