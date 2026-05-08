"""豆瓣电影数据采集工具 - 图形界面

免去记忆复杂命令行参数，通过鼠标点击即可完成参数配置。
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
from pathlib import Path
from tkinter import (
    Tk,
    StringVar,
    IntVar,
    BooleanVar,
    DoubleVar,
    filedialog,
    messagebox,
    ttk,
)
from tkinter.scrolledtext import ScrolledText
from typing import Any

# Add project root to sys.path so we can import modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Mode-specific default presets
# ---------------------------------------------------------------------------
MODE_META: dict[str, dict[str, Any]] = {
    "top250": {
        "label": "Top250 排行榜",
        "desc": "自动爬取豆瓣电影 Top250",
        "show_urls": False,
        "show_import_source": False,
    },
    "urls": {
        "label": "自定义 URL",
        "desc": "从指定链接爬取（支持列表/搜索页）",
        "show_urls": True,
        "show_import_source": False,
    },
    "import": {
        "label": "导入已有数据",
        "desc": "从本地 douban_items.json/CSV 重新生成 CSV 或存入 MySQL",
        "show_urls": False,
        "show_import_source": True,
    },
}


class GuiApp:
    """Main application window."""

    def __init__(self, root: Tk) -> None:
        self.root = root
        root.title("豆瓣电影数据采集工具")
        root.geometry("780x760")
        root.minsize(700, 700)

        # ── State variables ──────────────────────────────────────────────
        self.crawl_running = False
        self._stop_event = threading.Event()

        # Mode
        self.mode_var = StringVar(value="top250")

        # Crawl settings
        self.max_pages_var = IntVar(value=1)
        self.page_size_var = IntVar(value=25)
        self.comment_limit_var = IntVar(value=20)
        self.url_text_var = StringVar(value="")
        self.page_param_var = StringVar(value="start")

        # Feature toggles
        self.download_images_var = BooleanVar(value=True)
        self.crawl_details_var = BooleanVar(value=True)
        self.fast_mode_var = BooleanVar(value=False)

        # Anti-spider
        self.cookie_var = StringVar(value="")
        self.delay_min_var = DoubleVar(value=1.2)
        self.delay_max_var = DoubleVar(value=3.5)
        self.use_selenium_var = BooleanVar(value=False)
        self.show_browser_var = BooleanVar(value=False)
        self.driver_path_var = StringVar(value="")
        self.proxy_var = StringVar(value="")

        # MySQL
        self.save_mysql_var = BooleanVar(value=False)
        self.mysql_host_var = StringVar(value="localhost")
        self.mysql_port_var = IntVar(value=3306)
        self.mysql_user_var = StringVar(value="root")
        self.mysql_password_var = StringVar(value="123456")
        self.mysql_database_var = StringVar(value="douban")
        self.mysql_backup_var = StringVar(value="data/member_b/backup")

        # Output
        self.output_dir_var = StringVar(value="data/member_a")

        # ── Build UI ─────────────────────────────────────────────────────
        self._build_ui()

        # ── Bind mode switch ──────────────────────────────────────────────
        self.mode_var.trace_add("write", self._on_mode_changed)
        self._on_mode_changed()

        # ── Bind fast mode ────────────────────────────────────────────────
        self.fast_mode_var.trace_add("write", self._on_fast_mode)

    # ======================================================================
    # UI Construction
    # ======================================================================

    def _build_ui(self) -> None:
        """Construct the entire UI layout."""
        # Use a Notebook (tab) for cleaner grouping
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        # Tab 1: 采集设置
        crawl_frame = ttk.Frame(notebook, padding=10)
        notebook.add(crawl_frame, text=" 采集设置 ")

        # Tab 2: 存储设置
        storage_frame = ttk.Frame(notebook, padding=10)
        notebook.add(storage_frame, text=" 存储设置 ")

        # Bottom: 日志 + 按钮
        bottom_frame = ttk.Frame(self.root, padding=8)
        bottom_frame.pack(fill="both", expand=False)

        # ── Tab 1: 采集设置 ─────────────────────────────────────────────
        self._build_mode_section(crawl_frame)
        self._build_target_section(crawl_frame)
        self._build_feature_section(crawl_frame)
        self._build_antispider_section(crawl_frame)
        self._build_output_section(crawl_frame)

        # ── Tab 2: 存储设置 ─────────────────────────────────────────────
        self._build_mysql_section(storage_frame)

        # ── Log area + Button ────────────────────────────────────────────
        self._build_log_and_button(bottom_frame)

    # ------------------------------------------------------------------
    # Section: Mode
    # ------------------------------------------------------------------
    def _build_mode_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text=" 爬取模式 ", padding=8)
        frame.pack(fill="x", pady=(0, 6))

        for mode, meta in MODE_META.items():
            rb = ttk.Radiobutton(
                frame,
                text=f"{meta['label']}",
                variable=self.mode_var,
                value=mode,
            )
            rb.pack(anchor="w")
            tip = ttk.Label(frame, text=f"   {meta['desc']}", foreground="gray")
            tip.pack(anchor="w", padx=(18, 0))

        self._mode_tip = ttk.Label(frame, text="", foreground="#888")
        self._mode_tip.pack(anchor="w", padx=(18, 0), pady=(2, 0))

    # ------------------------------------------------------------------
    # Section: Target
    # ------------------------------------------------------------------
    def _build_target_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text=" 爬取目标 ", padding=8)
        frame.pack(fill="x", pady=6)

        row1 = ttk.Frame(frame)
        row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="最大页数:", width=10).pack(side="left")
        ttk.Spinbox(row1, from_=1, to=50, textvariable=self.max_pages_var, width=6).pack(
            side="left", padx=(0, 20)
        )
        ttk.Label(row1, text="每页条数:", width=10).pack(side="left")
        ttk.Spinbox(row1, from_=1, to=100, textvariable=self.page_size_var, width=6).pack(
            side="left"
        )

        row2 = ttk.Frame(frame)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="短评条数:", width=10).pack(side="left")
        ttk.Spinbox(row2, from_=0, to=200, textvariable=self.comment_limit_var, width=6).pack(
            side="left"
        )
        ttk.Label(row2, text="（0 表示不采集短评）", foreground="gray").pack(
            side="left", padx=(5, 0)
        )

        # Custom URLs area
        self._urls_frame = ttk.Frame(frame)
        self._urls_frame.pack(fill="x", pady=4)
        ttk.Label(self._urls_frame, text="自定义网址（每行一个）:").pack(anchor="w")
        self._url_text = ScrolledText(self._urls_frame, height=3, width=80)
        self._url_text.pack(fill="x", pady=(2, 0))

        # Page param
        row_page = ttk.Frame(self._urls_frame)
        row_page.pack(fill="x", pady=2)
        ttk.Label(row_page, text="分页参数名:").pack(side="left")
        ttk.Entry(row_page, textvariable=self.page_param_var, width=10).pack(side="left", padx=5)
        ttk.Label(row_page, text="（如 start / page，仅 urls 模式）", foreground="gray").pack(
            side="left"
        )

    # ------------------------------------------------------------------
    # Section: Features
    # ------------------------------------------------------------------
    def _build_feature_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text=" 功能选项 ", padding=8)
        frame.pack(fill="x", pady=6)

        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Checkbutton(row, text="下载封面图片", variable=self.download_images_var).pack(
            side="left", padx=(0, 15)
        )
        ttk.Checkbutton(row, text="采集详情页", variable=self.crawl_details_var).pack(
            side="left", padx=(0, 15)
        )
        ttk.Checkbutton(row, text="快速模式（高并发）", variable=self.fast_mode_var).pack(
            side="left"
        )

    # ------------------------------------------------------------------
    # Section: Anti-spider
    # ------------------------------------------------------------------
    def _build_antispider_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text=" 反爬与网络设置 ", padding=8)
        frame.pack(fill="x", pady=6)

        # Cookie
        row_cookie = ttk.Frame(frame)
        row_cookie.pack(fill="x", pady=2)
        ttk.Label(row_cookie, text="Cookie:").pack(side="left")
        ttk.Entry(row_cookie, textvariable=self.cookie_var, width=60).pack(
            side="left", padx=(5, 0), fill="x", expand=True
        )

        # Delay
        row_delay = ttk.Frame(frame)
        row_delay.pack(fill="x", pady=2)
        ttk.Label(row_delay, text="延迟范围:").pack(side="left")
        ttk.Spinbox(
            row_delay, from_=0.0, to=10.0, increment=0.1, textvariable=self.delay_min_var, width=5
        ).pack(side="left", padx=(5, 0))
        ttk.Label(row_delay, text="~").pack(side="left", padx=3)
        ttk.Spinbox(
            row_delay, from_=0.0, to=15.0, increment=0.1, textvariable=self.delay_max_var, width=5
        ).pack(side="left", padx=(0, 0))
        ttk.Label(row_delay, text="秒", foreground="gray").pack(side="left", padx=3)

        # Selenium
        row_selenium = ttk.Frame(frame)
        row_selenium.pack(fill="x", pady=2)
        ttk.Checkbutton(row_selenium, text="启用 Selenium 兜底", variable=self.use_selenium_var).pack(
            side="left", padx=(0, 15)
        )
        ttk.Checkbutton(row_selenium, text="显示浏览器窗口", variable=self.show_browser_var).pack(
            side="left", padx=(0, 15)
        )
        ttk.Label(row_selenium, text="ChromeDriver:").pack(side="left")
        ttk.Entry(row_selenium, textvariable=self.driver_path_var, width=25).pack(
            side="left", padx=5
        )
        ttk.Button(row_selenium, text="浏览", command=self._browse_driver).pack(side="left")

        # Proxy
        row_proxy = ttk.Frame(frame)
        row_proxy.pack(fill="x", pady=2)
        ttk.Label(row_proxy, text="代理:").pack(side="left")
        ttk.Entry(row_proxy, textvariable=self.proxy_var, width=60).pack(
            side="left", padx=(5, 0), fill="x", expand=True
        )

    # ------------------------------------------------------------------
    # Section: Output
    # ------------------------------------------------------------------
    def _build_output_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text=" 输出目录 ", padding=8)
        frame.pack(fill="x", pady=6)

        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.output_dir_var, width=60).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(row, text="浏览", command=self._browse_output_dir).pack(side="left", padx=5)

    # ------------------------------------------------------------------
    # Section: MySQL
    # ------------------------------------------------------------------
    def _build_mysql_section(self, parent: ttk.Frame) -> None:
        # Save toggle
        toggle_frame = ttk.Frame(parent)
        toggle_frame.pack(fill="x", pady=(0, 6))
        self._mysql_checkbox = ttk.Checkbutton(
            toggle_frame,
            text="保存到 MySQL 数据库",
            variable=self.save_mysql_var,
        )
        self._mysql_checkbox.pack(side="left")

        # MySQL settings
        settings_frame = ttk.LabelFrame(parent, text=" MySQL 连接参数 ", padding=8)
        settings_frame.pack(fill="x", pady=6)

        grid = ttk.Frame(settings_frame)
        grid.pack(fill="x")

        # Row 1: Host + Port
        r1 = ttk.Frame(grid)
        r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="主机:", width=12).pack(side="left")
        ttk.Entry(r1, textvariable=self.mysql_host_var, width=20).pack(side="left", padx=(0, 15))
        ttk.Label(r1, text="端口:", width=6).pack(side="left")
        ttk.Spinbox(r1, from_=1, to=65535, textvariable=self.mysql_port_var, width=7).pack(
            side="left"
        )

        # Row 2: User + Password
        r2 = ttk.Frame(grid)
        r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="用户名:", width=12).pack(side="left")
        ttk.Entry(r2, textvariable=self.mysql_user_var, width=20).pack(side="left", padx=(0, 15))
        ttk.Label(r2, text="密码:", width=6).pack(side="left")
        ttk.Entry(r2, textvariable=self.mysql_password_var, width=20, show="*").pack(side="left")

        # Row 3: Database + Backup
        r3 = ttk.Frame(grid)
        r3.pack(fill="x", pady=2)
        ttk.Label(r3, text="数据库名:", width=12).pack(side="left")
        ttk.Entry(r3, textvariable=self.mysql_database_var, width=20).pack(side="left", padx=(0, 15))
        ttk.Label(r3, text="备份目录:", width=8).pack(side="left")
        ttk.Entry(r3, textvariable=self.mysql_backup_var, width=25).pack(
            side="left", padx=(0, 5), fill="x", expand=True
        )
        ttk.Button(r3, text="浏览", command=self._browse_backup_dir).pack(side="left")

    # ------------------------------------------------------------------
    # Log + Button
    # ------------------------------------------------------------------
    def _build_log_and_button(self, parent: ttk.Frame) -> None:
        # Log
        log_frame = ttk.LabelFrame(parent, text=" 运行日志 ", padding=4)
        log_frame.pack(fill="both", expand=True, pady=(0, 6))

        self.log_area = ScrolledText(
            log_frame, height=12, width=90, state="disabled", wrap="word"
        )
        self.log_area.pack(fill="both", expand=True)

        # Button
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill="x")

        self._start_btn = ttk.Button(
            btn_frame, text="📥 开始采集", command=self._start_crawl
        )
        self._start_btn.pack(side="right", padx=(5, 0))
        self._stop_btn = ttk.Button(
            btn_frame, text="⏹ 停止", command=self._stop_crawl, state="disabled"
        )
        self._stop_btn.pack(side="right")

    # ======================================================================
    # Handlers
    # ======================================================================

    def _on_mode_changed(self, *args: Any) -> None:
        """Show/hide URL textarea based on selected mode."""
        mode = self.mode_var.get()
        meta = MODE_META.get(mode, {})
        if meta.get("show_urls"):
            self._urls_frame.pack(fill="x", pady=4)
        else:
            self._urls_frame.pack_forget()

    def _on_fast_mode(self, *args: Any) -> None:
        """When fast mode is toggled, auto-adjust delay settings."""
        if self.fast_mode_var.get():
            self.delay_min_var.set(0.5)
            self.delay_max_var.set(1.5)

    def _browse_driver(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 chromedriver.exe",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")],
        )
        if path:
            self.driver_path_var.set(path)

    def _browse_output_dir(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_dir_var.set(path)

    def _browse_backup_dir(self) -> None:
        path = filedialog.askdirectory(title="选择备份目录")
        if path:
            self.mysql_backup_var.set(path)

    # ======================================================================
    # Logging
    # ======================================================================

    def _log(self, msg: str) -> None:
        """Append a line to the log area."""
        self.log_area.configure(state="normal")
        self.log_area.insert("end", msg + "\n")
        self.log_area.see("end")
        self.log_area.configure(state="disabled")
        self.root.update_idletasks()

    # ======================================================================
    # Crawl Logic (runs in background thread)
    # ======================================================================

    def _start_crawl(self) -> None:
        """Validate inputs and start crawling in a background thread."""
        if self.crawl_running:
            return

        mode = self.mode_var.get()

        # Validation for urls mode
        if mode == "urls":
            urls_text = self._url_text.get("1.0", "end-1c").strip()
            if not urls_text:
                messagebox.showerror("参数错误", "自定义 URL 模式下，请至少输入一个网址。")
                return

        # Build config dict from UI
        config_data = self._collect_config(mode)

        # Start background thread
        self._stop_event.clear()
        self.crawl_running = True
        self._toggle_ui(disabled=True)
        self.log_area.configure(state="normal")
        self.log_area.delete("1.0", "end")
        self.log_area.configure(state="disabled")
        self._log("🚀 开始采集任务...")

        thread = threading.Thread(
            target=self._run_task,
            args=(config_data,),
            daemon=True,
        )
        thread.start()

    def _collect_config(self, mode: str) -> dict[str, Any]:
        """Read all current UI values into a config dict."""
        # Read custom URLs
        urls: list[str] = []
        if mode == "urls":
            text = self._url_text.get("1.0", "end-1c").strip()
            urls = [u.strip() for u in text.splitlines() if u.strip()]

        proxy_str = self.proxy_var.get().strip()
        proxies: list[str] = [proxy_str] if proxy_str else []

        return {
            "mode": mode,
            "urls": urls,
            "max_pages": self.max_pages_var.get(),
            "page_param": self.page_param_var.get(),
            "page_size": self.page_size_var.get(),
            "comment_limit": self.comment_limit_var.get(),
            "download_images": self.download_images_var.get(),
            "crawl_details": self.crawl_details_var.get(),
            "fast_mode": self.fast_mode_var.get(),
            "cookie": self.cookie_var.get().strip() or None,
            "delay_min": self.delay_min_var.get(),
            "delay_max": self.delay_max_var.get(),
            "use_selenium": self.use_selenium_var.get(),
            "show_browser": self.show_browser_var.get(),
            "driver_path": self.driver_path_var.get().strip() or None,
            "proxies": proxies,
            "output_dir": self.output_dir_var.get().strip() or "data/member_a",
            "save_mysql": self.save_mysql_var.get(),
            "mysql_host": self.mysql_host_var.get().strip() or "localhost",
            "mysql_port": self.mysql_port_var.get(),
            "mysql_user": self.mysql_user_var.get().strip() or "root",
            "mysql_password": self.mysql_password_var.get().strip() or "123456",
            "mysql_database": self.mysql_database_var.get().strip() or "douban",
            "mysql_backup_dir": self.mysql_backup_var.get().strip() or "data/member_b/backup",
        }

    def _run_task(self, cfg: dict[str, Any]) -> None:
        """Execute the crawl/import task."""
        try:
            if cfg["mode"] == "import":
                self._run_import_task(cfg)
            else:
                self._run_crawl_task(cfg)

            if not self._stop_event.is_set():
                self._log("✅ 任务完成！")

            if cfg["save_mysql"] and not self._stop_event.is_set():
                self._log("💾 MySQL 存储完成。")
        except Exception as exc:
            if self._stop_event.is_set():
                self._log("⏹ 任务已停止。")
            else:
                self._log(f"❌ 出错：{exc}")
        finally:
            self.crawl_running = False
            self.root.after(0, lambda: self._toggle_ui(disabled=False))

    def _run_crawl_task(self, cfg: dict[str, Any]) -> None:
        """Run the crawl workflow (top250 or urls)."""
        from member_a_douban.config import CrawlConfig
        from member_a_douban.crawler import DoubanCrawler, expand_paginated_urls, save_items
        from member_a_douban.cleaner import clean_items

        output_dir = Path(cfg["output_dir"])
        image_dir = output_dir / "images"

        proxy_pool = self._build_proxy_pool(cfg["proxies"])

        detail_workers = 4 if cfg["fast_mode"] else 1
        image_workers = 6 if cfg["fast_mode"] else 1
        delay_min = 0.5 if cfg["fast_mode"] else cfg["delay_min"]
        delay_max = 1.5 if cfg["fast_mode"] else cfg["delay_max"]

        config = CrawlConfig(
            output_dir=output_dir,
            image_dir=image_dir,
            max_pages=cfg["max_pages"],
            page_param=cfg["page_param"],
            page_size=max(1, cfg["page_size"]),
            proxies=proxy_pool[0] if len(proxy_pool) == 1 else None,
            proxy_pool=proxy_pool if len(proxy_pool) > 1 else (),
            cookie=cfg["cookie"],
            use_selenium=cfg["use_selenium"],
            selenium_headless=not cfg["show_browser"],
            chrome_driver_path=cfg["driver_path"],
            download_images=cfg["download_images"],
            crawl_details=cfg["crawl_details"],
            comment_limit=max(0, cfg["comment_limit"]),
            detail_workers=detail_workers,
            image_workers=image_workers,
            delay_min=delay_min,
            delay_max=delay_max,
        )

        self._log(f"📂 输出目录：{output_dir}")
        self._log(f"📄 采集页数：{cfg['max_pages']}")
        self._log(f"💬 短评条数：{cfg['comment_limit']}")
        if cfg["cookie"]:
            self._log("🔑 已注入 Cookie")
        if cfg["use_selenium"] or cfg["driver_path"]:
            self._log("🌐 Selenium 兜底已启用")
        if cfg["download_images"]:
            self._log("🖼️ 将下载封面图片")
        if cfg["save_mysql"]:
            self._log(f"🗄️ 将保存到 MySQL：{cfg['mysql_host']}:{cfg['mysql_port']}/{cfg['mysql_database']}")

        crawler = DoubanCrawler(config)

        self._log("🔄 正在采集数据...")
        if cfg["mode"] == "urls":
            if not cfg["urls"]:
                raise ValueError("自定义 URL 模式下必须提供网址")
            items = crawler.crawl_urls(expand_paginated_urls(cfg["urls"], config))
        else:
            items = crawler.crawl_movie_top250()

        if self._stop_event.is_set():
            return

        if not items:
            self._log("⚠️ 未采集到任何数据。")
            return

        self._log(f"✅ 采集到 {len(items)} 条数据，正在清洗...")
        clean_items(items)

        json_path, csv_path = save_items(items, config.output_dir)
        self._log(f"📄 JSON 已保存：{json_path}")
        self._log(f"📄 CSV 已保存：{csv_path}")

        # Save to MySQL
        if cfg["save_mysql"] and items:
            self._save_to_mysql(items, cfg)

    @staticmethod
    def _resolve_path(p: str) -> Path:
        """Resolve relative path against PROJECT_ROOT; absolute paths stay as-is."""
        path = Path(p)
        if path.is_absolute():
            return path
        return PROJECT_ROOT / path

    def _run_import_task(self, cfg: dict[str, Any]) -> None:
        """Run the import workflow."""
        from member_a_douban.cleaner import clean_items
        from member_a_douban.parser import DoubanItem

        import csv
        import json

        output_dir = self._resolve_path(cfg["output_dir"])
        json_path = output_dir / "douban_items.json"
        csv_path_in = output_dir / "douban_items.csv"

        self._log(f"📂 从 {output_dir} 导入数据...")

        if json_path.exists():
            with json_path.open("r", encoding="utf-8") as f:
                raw_data = json.load(f)
            self._log(f"✅ 从 JSON 读取 {len(raw_data)} 条数据")
        elif csv_path_in.exists():
            with csv_path_in.open("r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                raw_data = list(reader)
            self._log(f"✅ 从 CSV 读取 {len(raw_data)} 条数据")
        else:
            self._log(f"❌ 未找到文件：{json_path} 或 {csv_path_in}")
            return

        items = []
        for d in raw_data:
            if "runtime" in d and d["runtime"] == "":
                d["runtime"] = None
            items.append(DoubanItem(**d))

        clean_items(items)
        self._log(f"✅ 清洗完成，共 {len(items)} 条数据")

        # Save to MySQL
        if cfg["save_mysql"] and items:
            self._save_to_mysql(items, cfg)

    def _save_to_mysql(self, items: list, cfg: dict[str, Any]) -> None:
        """Save items to MySQL."""
        from member_b_douban import save_to_mysql

        mode = cfg["mode"]
        backup_dir = str(self._resolve_path(cfg["mysql_backup_dir"]))
        self._log("🗄️ 正在写入 MySQL...")
        inserted = save_to_mysql(
            [item.to_dict() for item in items],
            recreate=(mode == "import" or mode == "top250"),
            host=cfg["mysql_host"],
            port=cfg["mysql_port"],
            user=cfg["mysql_user"],
            password=cfg["mysql_password"],
            database=cfg["mysql_database"],
            backup_dir=backup_dir,
        )
        self._log(f"✅ MySQL 写入 {inserted} 条记录")
        self._log(f"📂 备份已导出到 {backup_dir}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_proxy_pool(proxy_urls: list[str]) -> tuple[dict[str, str], ...]:
        proxies = []
        for proxy_url in proxy_urls:
            proxy_url = proxy_url.strip()
            if not proxy_url:
                continue
            proxies.append({"http": proxy_url, "https": proxy_url})
        return tuple(proxies)

    def _toggle_ui(self, disabled: bool) -> None:
        """Enable or disable UI elements during crawl."""
        if disabled:
            self._start_btn.configure(state="disabled")
            self._stop_btn.configure(state="normal")
        else:
            self._start_btn.configure(state="normal")
            self._stop_btn.configure(state="disabled")

    def _stop_crawl(self) -> None:
        """Request crawl to stop."""
        self._stop_event.set()
        self._log("⏹ 正在停止（等待当前任务完成）...")


# ======================================================================
# Entry point
# ======================================================================


def main() -> None:
    root = Tk()
    app = GuiApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
