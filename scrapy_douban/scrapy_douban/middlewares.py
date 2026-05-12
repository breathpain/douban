"""豆瓣 Scrapy 爬虫的下载器中间件。

提供：
- ``RandomUserAgentMiddleware`` – 每个请求轮换 User-Agent
- ``ProxyMiddleware`` – 应用代理设置
- ``AntiSpiderRetryMiddleware`` – 检测反爬虫封锁并重试
- ``RandomDelayMiddleware`` – 细粒度延迟控制
"""

from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING

from scrapy import Request, signals
from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy.exceptions import IgnoreRequest, NotConfigured

try:
    from requests_douban.anti_spider import (
        BLOCK_TITLE_PATTERNS,
        choose_user_agent,
        is_blocked,
        parse_cookie,
    )
    from requests_douban.config import CrawlConfig, DEFAULT_USER_AGENTS
    from requests_douban.http_client import _extract_title
except ImportError:
    # 当 requests_douban 不可导入时的回退定义
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
# 1. 随机 User-Agent 中间件
# ---------------------------------------------------------------------------

class RandomUserAgentMiddleware:
    """从可配置的元组中轮换 User-Agent。"""

    def __init__(self, user_agents: tuple[str, ...]) -> None:
        self.user_agents = user_agents

    @classmethod
    def from_crawler(cls, crawler) -> RandomUserAgentMiddleware:
        ua_tuple: tuple[str, ...] = tuple(
            crawler.settings.getlist("USER_AGENT_LIST")
        ) or getattr(DEFAULT_USER_AGENTS, "_fields", DEFAULT_USER_AGENTS)

        # 如果设置中未提供 UA 列表，回退到默认值
        if not ua_tuple:
            ua_tuple = DEFAULT_USER_AGENTS
        return cls(ua_tuple)

    def process_request(self, request: Request, spider) -> Request | None:
        request.headers["User-Agent"] = choose_user_agent(self.user_agents)
        return None


# ---------------------------------------------------------------------------
# 2. 代理中间件
# ---------------------------------------------------------------------------

class ProxyMiddleware:
    """通过 Scrapy 配置为每个请求应用代理。"""

    def __init__(self, proxies: tuple[dict[str, str], ...] | None = None) -> None:
        self.proxies = proxies or ()

    @classmethod
    def from_crawler(cls, crawler) -> ProxyMiddleware:
        from requests_douban.config import CrawlConfig
        # 尝试从 CrawlConfig 读取（当通过 app.py 运行时）
        if CrawlConfig is not None:
            try:
                member_a_config: CrawlConfig = getattr(crawler, "member_a_config", None)  # type: ignore[union-attr]
                if member_a_config and member_a_config.proxy_pool:
                    return cls(member_a_config.proxy_pool)
                if member_a_config and member_a_config.proxies:
                    return cls((member_a_config.proxies,))
            except Exception:
                pass

        # 回退到 settings 配置
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
# 3. 反爬虫重试中间件
# ---------------------------------------------------------------------------

class AntiSpiderRetryMiddleware(RetryMiddleware):
    """扩展内置 RetryMiddleware，检测豆瓣反爬虫页面。

    对返回 200 OK 的响应检测其是否为封锁页面（标题、关键词），
    如果是则当作错误响应进行重试。
    """

    def process_response(self, request: Request, response, spider):
        if response.status == 200:
            html = response.text

            # 将 Scrapy Headers（字节值）转为字符串以供给 is_blocked 使用
            str_headers: dict[str, str] = {}
            for k, v in response.headers.items():
                key = k.decode("utf-8", errors="replace").lower()
                # Scrapy Headers 以 list[bytes] 形式存储值
                if isinstance(v, (list, tuple)):
                    str_headers[key] = v[0].decode("utf-8", errors="replace") if v else ""
                else:
                    str_headers[key] = v.decode("utf-8", errors="replace")

            # 通过 is_blocked 检查（状态码 + 关键词）
            if is_blocked(response.status, html, str_headers):
                reason = "Anti-spider block (content keywords)"
                return self._retry(request, reason, spider) or response

            # 检查 <title> 模式
            title = _extract_title(html)
            if title and any(p in title for p in BLOCK_TITLE_PATTERNS):
                reason = f"Anti-spider block (title={title[:40]})"
                return self._retry(request, reason, spider) or response

        return super().process_response(request, response, spider)


# ---------------------------------------------------------------------------
# 4. 随机延迟中间件
# ---------------------------------------------------------------------------

class RandomDelayMiddleware:
    """确保每个请求之前都有随机延迟。

    与 Scrapy 内置的 DOWNLOAD_DELAY 不同（后者是 per-slot 且固定值），
    此中间件对每个请求在 [min, max] 秒范围内施加随机延迟。
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
# 5. Cookie 中间件（如果提供了豆瓣 Cookie 则注入）
# ---------------------------------------------------------------------------

class DoubanCookieMiddleware:
    """将豆瓣 Cookie 注入每个请求。"""

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
            # 直接构建 Cookie 头（比 request.cookies 更新更可靠）
            cookie_str = "; ".join(f"{k}={v}" for k, v in self.cookie_dict.items())
            request.headers["Cookie"] = cookie_str
            # 阻止 CookiesMiddleware 覆盖我们的 Cookie 头
            request.meta["dont_merge_cookies"] = True
            # 同时保留 request.cookies 作为备用
            request.cookies.update(self.cookie_dict)
