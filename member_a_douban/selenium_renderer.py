"""Optional Selenium renderer for JavaScript-heavy or blocked pages."""

from __future__ import annotations

from contextlib import AbstractContextManager

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.webdriver import WebDriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise ModuleNotFoundError(
        "selenium is required for --use-selenium. Install dependencies with: pip install -r requirements.txt"
    ) from exc

from .anti_spider import choose_user_agent, parse_cookie, polite_sleep
from .config import CrawlConfig
from .http_client import HttpResult


class SeleniumRenderer(AbstractContextManager["SeleniumRenderer"]):
    def __init__(self, config: CrawlConfig) -> None:
        self.config = config
        self.driver: WebDriver | None = None
        self.cookies_loaded = False

    def __enter__(self) -> "SeleniumRenderer":
        options = Options()
        if self.config.selenium_headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1366,900")
        options.add_argument(f"--user-agent={choose_user_agent(self.config.user_agents)}")
        if self.config.chrome_driver_path:
            self.driver = self._create_driver_with_path(options, self.config.chrome_driver_path)
        else:
            self.driver = webdriver.Chrome(options=options)
        return self

    def _create_driver_with_path(self, options: Options, driver_path: str) -> WebDriver:
        try:
            service = Service(executable_path=driver_path)
            return webdriver.Chrome(service=service, options=options)
        except TypeError:
            return webdriver.Chrome(executable_path=driver_path, options=options)

    def __exit__(self, exc_type, exc, traceback) -> None:  # type: ignore[no-untyped-def]
        if self.driver:
            self.driver.quit()
            self.driver = None

    def render(self, url: str) -> HttpResult:
        if not self.driver:
            raise RuntimeError("SeleniumRenderer must be used as a context manager")

        self._load_cookies()
        self.driver.get(url)
        WebDriverWait(self.driver, self.config.request_timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        polite_sleep(self.config.delay_min, self.config.delay_max)
        return HttpResult(
            url=self.driver.current_url,
            status_code=200,
            text=self.driver.page_source,
            used_selenium=True,
        )

    def _load_cookies(self) -> None:
        if self.cookies_loaded or not self.config.cookie:
            return
        if not self.driver:
            raise RuntimeError("SeleniumRenderer must be used as a context manager")

        self.driver.get("https://www.douban.com/")
        for name, value in parse_cookie(self.config.cookie).items():
            self.driver.add_cookie(
                {
                    "name": name,
                    "value": value,
                    "domain": ".douban.com",
                    "path": "/",
                }
            )
        self.cookies_loaded = True
