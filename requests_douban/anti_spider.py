"""反爬虫小工具，帮助实现礼貌爬取。"""
from __future__ import annotations

import random
import time
from collections.abc import Mapping


BLOCK_KEYWORDS = (
    "captcha",
    "sec.douban.com",
    "检测到有异常请求",
    "访问过于频繁",
    "请求过于频繁",
    "你的访问似乎不太对劲",
    "你的请求不合法",
    "暂时无法访问",
    "需要安全验证",
    "请输入验证码",
    "请登录后重试",
    "请重新尝试",
    "无法访问",
    "forbidden",
    "403 Forbidden",
    "access denied",
)


BLOCK_TITLE_PATTERNS = (
    "访问异常",
    "安全验证",
    "操作过于频繁",
)


def choose_user_agent(user_agents: tuple[str, ...]) -> str:
    return random.choice(user_agents)


def polite_sleep(delay_min: float, delay_max: float) -> None:
    time.sleep(random.uniform(delay_min, delay_max))

def choose_proxy(
    proxies: dict[str, str] | None,
    proxy_pool: tuple[dict[str, str], ...] = (),
) -> dict[str, str] | None:
    if proxy_pool:
        return random.choice(proxy_pool)
    return proxies


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

