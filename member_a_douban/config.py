"""Runtime configuration for the Douban crawler."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
)


@dataclass
class CrawlConfig:
    """Settings that keep scraping behavior polite and easy to tune."""

    output_dir: Path = Path("data/member_a")
    image_dir: Path = Path("data/member_a/images")
    request_timeout: int = 15
    retry_times: int = 3
    delay_min: float = 1.0
    delay_max: float = 4.0
    max_pages: int = 10
    use_selenium: bool = False
    selenium_headless: bool = True
    chrome_driver_path: str | None = None
    download_images: bool = True
    crawl_details: bool = True
    comment_limit: int = 15
    detail_workers: int = 1
    image_workers: int = 1
    proxies: dict[str, str] | None = None
    proxy_pool: tuple[dict[str, str], ...] = ()
    page_param: str = "start"
    page_size: int = 25
    cookie: str | None = None
    user_agents: tuple[str, ...] = field(default_factory=lambda: DEFAULT_USER_AGENTS)
