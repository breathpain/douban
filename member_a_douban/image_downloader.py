"""Image download utilities."""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise ModuleNotFoundError(
        "requests is required. Install dependencies with: pip install -r requirements.txt"
    ) from exc

from .anti_spider import choose_user_agent, polite_sleep
from .config import CrawlConfig


def download_image(url: str, output_dir: Path, config: CrawlConfig) -> Path | None:
    if not url:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": choose_user_agent(config.user_agents),
        "Referer": "https://www.douban.com/",
    }
    response = requests.get(
        url,
        headers=headers,
        proxies=config.proxies,
        timeout=config.request_timeout,
        stream=True,
    )
    response.raise_for_status()

    content_type = response.headers.get("content-type", "").split(";")[0]
    suffix = mimetypes.guess_extension(content_type) or Path(urlparse(url).path).suffix or ".jpg"
    filename = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + suffix
    target = output_dir / filename

    with target.open("wb") as file:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                file.write(chunk)

    polite_sleep(config.delay_min / 2, config.delay_max / 2)
    return target
