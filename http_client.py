"""Requests-based client with retry, delay, cookies, and rotating headers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

try:
    import requests
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise ModuleNotFoundError(
        "requests is required. Install dependencies with: pip install -r requirements.txt"
    ) from exc

from .anti_spider import choose_user_agent, is_blocked, parse_cookie, polite_sleep
from .config import CrawlConfig


DOUBAN_REFERER: Final = "https://www.douban.com/"


class BlockedByDoubanError(RuntimeError):
    """Raised when Douban returns an obvious anti-spider page."""


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
        self.session.cookies.update(parse_cookie(config.cookie))

    def get(self, url: str) -> HttpResult:
        last_error: Exception | None = None

        for attempt in range(1, self.config.retry_times + 1):
            headers = self._headers()
            try:
                response = self.session.get(
                    url,
                    headers=headers,
                    proxies=self.config.proxies,
                    timeout=self.config.request_timeout,
                )
                text = response.text
                if is_blocked(response.status_code, text, response.headers):
                    raise BlockedByDoubanError(
                        f"blocked by Douban, status={response.status_code}, url={url}"
                    )
                response.raise_for_status()
                return HttpResult(url=response.url, status_code=response.status_code, text=text)
            except (requests.RequestException, BlockedByDoubanError) as exc:
                last_error = exc
                if attempt < self.config.retry_times:
                    polite_sleep(self.config.delay_min, self.config.delay_max)

        raise RuntimeError(f"failed to fetch {url}: {last_error}") from last_error

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": choose_user_agent(self.config.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Referer": DOUBAN_REFERER,
        }
