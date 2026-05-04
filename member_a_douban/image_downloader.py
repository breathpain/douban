"""Image download utilities."""

from __future__ import annotations

import mimetypes
import re
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


def download_image(
    url: str,
    output_dir: Path,
    config: CrawlConfig,
    filename_stem: str | None = None,
) -> Path | None:
    if not url:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    url_suffix = Path(urlparse(url).path).suffix or ".jpg"
    stem = _safe_filename_stem(filename_stem or Path(urlparse(url).path).stem or "image")
    target = output_dir / f"{stem}{url_suffix}"
    if target.exists() and target.stat().st_size > 0:
        return target
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
    suffix = mimetypes.guess_extension(content_type) or url_suffix
    if suffix != url_suffix:
        target = output_dir / f"{stem}{suffix}"
        if target.exists() and target.stat().st_size > 0:
            return target

    with target.open("wb") as file:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                file.write(chunk)

    polite_sleep(config.delay_min / 2, config.delay_max / 2)
    return target


def _safe_filename_stem(value: str) -> str:
    stem = re.sub(r'[\\/:*?"<>|]+', "_", value)
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    return stem[:120] or "image"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    for index in range(2, 10000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"too many duplicate image filenames for {path.name}")
