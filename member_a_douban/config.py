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
    delay_min: float = 1.2
    delay_max: float = 3.5
    max_pages: int = 1
    use_selenium: bool = False
    selenium_headless: bool = True
    download_images: bool = True
    proxies: dict[str, str] | None = None
    cookie: str | None = None
    user_agents: tuple[str, ...] = field(default_factory=lambda: DEFAULT_USER_AGENTS)
