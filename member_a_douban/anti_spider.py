"""Small anti-spider helpers for respectful crawling."""
from __future__ import annotations

import random
import time
from collections.abc import Mapping


BLOCK_KEYWORDS = (
    "captcha",
    "sec.douban.com",
    "检测到有异常请求",
    "访问过于频繁",
    "forbidden",
    "403 Forbidden",
)


def choose_user_agent(user_agents: tuple[str, ...]) -> str:
    return random.choice(user_agents)


def polite_sleep(delay_min: float, delay_max: float) -> None:
    time.sleep(random.uniform(delay_min, delay_max))


def parse_cookie(cookie: str | None) -> dict[str, str]:
    if not cookie:
        return {}

    pairs: dict[str, str] = {}
    for part in cookie.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if key:
            pairs[key] = value.strip()
    return pairs


def is_blocked(status_code: int, html: str, headers: Mapping[str, str] | None = None) -> bool:
    if status_code in {403, 418, 429}:
        return True

    lowered = html.lower()
    if any(keyword.lower() in lowered for keyword in BLOCK_KEYWORDS):
        return True

    content_type = ""
    if headers:
        content_type = headers.get("content-type", "")
    return bool(html) and "text/html" not in content_type.lower() and status_code >= 400

