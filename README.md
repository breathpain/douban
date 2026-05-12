# 豆瓣电影数据采集与分析系统

豆瓣电影一站式数据平台：支持 **requests / Scrapy 双引擎爬虫**、**Selenium 反爬兜底**、**MySQL 双表持久化**、**交互式 Web 仪表盘** 与 **数据可视化分析**。

---

## 目录

- [项目概述](#项目概述)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [模块一：requests 爬虫（requests_douban）](#模块一requests-爬虫requests_douban)
  - [CLI 命令总览](#cli-命令总览)
  - [爬取模式](#爬取模式)
  - [完整参数表](#完整参数表)
  - [常用示例](#常用示例)
- [模块二：Scrapy 爬虫（scrapy_douban）](#模块二scrapy-爬虫scrapy_douban)
  - [启动方式](#启动方式)
  - [Spider 说明](#spider-说明)
  - [中间件与管道](#中间件与管道)
  - [常用示例](#scrapy-常用示例)
- [模块三：MySQL 存储（database_service）](#模块三mysql-存储database_service)
  - [Python API](#python-api)
  - [数据库表结构](#数据库表结构)
  - [数据去重与增量导入](#数据去重与增量导入)
- [模块四：数据分析与 Web 仪表盘（analysis）](#模块四数据分析与-web-仪表盘analysis)
  - [数据分析脚本](#数据分析脚本)
  - [Web 仪表盘](#web-仪表盘)
- [辅助工具](#辅助工具)
  - [爬虫基准测试（bench_compare.py）](#爬虫基准测试bench_comparepy)
  - [数据验证（_check_data.py）](#数据验证_check_datapy)
- [数据文件格式](#数据文件格式)
- [爬虫数据流全景](#爬虫数据流全景)
- [合规提醒](#合规提醒)

---

## 项目概述

本项目围绕豆瓣电影数据，构建了从采集、清洗、存储到分析可视化的完整数据管线：

| 模块 | 定位 | 核心技术 |
|---|---|---|
| **requests_douban** | Requests 爬虫引擎 | `requests` + `BeautifulSoup` + `ThreadPoolExecutor` |
| **scrapy_douban** | Scrapy 爬虫引擎 | `Scrapy` 异步框架，复用 requests_douban 解析器 |
| **database_service** | MySQL 存储与备份 | `pymysql` 双表存储 + JSON/CSV 备份导出 |
| **analysis** | 分析 + Web 仪表盘 | `Flask` + `Plotly` + `pandas` + `matplotlib` + `seaborn` |

**核心能力**：

- 自动翻页分页采集、详情页 & 短评逐页抓取
- 多线程并发（详情页/图片）加速采集
- 自适应反爬：随机 UA + 随机延迟 + Cookie 注入 + 代理池轮换 + 反爬页面多维度检测
- 桌面版 → 移动版 → Selenium 三级降级策略
- 数据清洗管线：字段去空格/中文 NBSP 替换、数值类型标准化（rating→float, runtime→int）
- MySQL 双表存储，URL 唯一键去重，短评结构化拆分
- 交互式 Web 仪表盘（16+ Plotly 图表、类型/国家/年代联动筛选、实时爬虫控制）

---

## 项目结构

```
F:\douban\
│
├── requests_douban/              # 【模块一】Requests 爬虫引擎
│   ├── cli.py                    #   命令行入口（所有参数定义）
│   ├── crawler.py                #   爬虫工作流编排（列表→详情→短评→图片）
│   ├── config.py                 #   CrawlConfig 配置数据类
│   ├── http_client.py            #   HTTP 客户端（Session/重试/UA轮换/代理）
│   ├── parser.py                 #   HTML 解析器（桌面版/移动版/JSON-LD/Rexxar API）
│   ├── anti_spider.py            #   反爬检测（标题/关键词/状态码多维度）
│   ├── image_downloader.py       #   图片下载（带缓存、以电影名命名）
│   ├── selenium_renderer.py      #   Selenium 渲染器（支持页面滚动/加载更多评论）
│   └── cleaner.py                #   数据清洗管线（NBSP/runtime/rating 标准化）
│
├── scrapy_douban/                # 【模块二】Scrapy 异步爬虫引擎
│   ├── scrapy.cfg                #   Scrapy 项目配置
│   └── scrapy_douban/
│       ├── items.py              #   Scrapy Item 定义
│       ├── settings.py           #   设置（并发/延迟/UA/代理/管道）
│       ├── middlewares.py        #   中间件（UA旋转/代理/反爬重试/Cookie）
│       ├── pipelines.py          #   管道（清洗/图片/导出）
│       └── spiders/
│           ├── top250.py         #   Top250 Spider（复用 requests_douban 解析+降级）
│           └── custom.py         #   自定义 URL Spider
│
├── database_service/             # 【模块三】MySQL 存储与备份
│   ├── __init__.py               #   统一入口（save_to_mysql / export_backup）
│   ├── config.py                 #   MySQLConfig 连接配置
│   ├── database.py               #   建库/建表/迁移
│   ├── repository.py             #   DAO 层（插入+去重+跳过已存在）
│   └── exporter.py               #   备份导出（嵌套 JSON + CSV×2）
│
├── analysis/                     # 【模块四】数据分析与 Web 服务
│   ├── douban_analysis.py        #   数据分析脚本（清洗→统计→可视化）
│   ├── web_server.py             #   Flask Web 仪表盘（爬虫控制+图表+数据库管理）
│   ├── download_deps.py          #   下载前端依赖（jQuery/DataTables）
│   └── output/                   #   图表输出目录
│
├── data/                         #   数据目录（gitignored）
│   ├── crawler/                  #     爬虫输出（douban_items.json / csv / images/）
│   └── database/backup/          #     MySQL 备份（douban_movies.json / csv）
│
├── bench_compare.py              # 爬虫基准测试脚本（Scrapy vs Requests）
├── run_scrapy_spider.py          # Scrapy Spider 便捷启动器
├── test_comments.py              # 短评解析测试（HTTP + Selenium）
├── _check_data.py                # 数据质量快速检查
├── chromedriver.exe              # ChromeDriver（Selenium 依赖）
├── requirements.txt              # Python 依赖
└── .gitignore
```

---

## 快速开始

### 1. 安装依赖

```powershell
pip install -r requirements.txt
```

| 包名 | 用途 | 是否必须 |
|---|---|---|
| `beautifulsoup4` `lxml` | HTML 解析 | ✅ |
| `requests` | HTTP 客户端 | ✅ |
| `tqdm` | 进度条显示 | ✅ |
| `Scrapy` | 异步爬虫引擎 | ❌（仅 Scrapy 模块需要） |
| `selenium` | 动态页面渲染 | ❌（仅 `--use-selenium` 需要） |
| `pymysql` `cryptography` | MySQL 连接 | ❌（仅 `--save-mysql` 需要） |
| `flask` `plotly` `pandas` `numpy` | Web 仪表盘 | ❌（仅 analysis 模块需要） |

### 2. 三步快速体验

```powershell
# Step 1: 采集 Top250 第 1 页（含详情 + 短评 + 图片）
python -m requests_douban.cli --mode top250 --max-pages 1

# Step 2: 将爬取结果存入 MySQL
python -m requests_douban.cli --mode import --save-mysql

# Step 3: 启动 Web 仪表盘
python analysis/web_server.py
```

浏览器访问 `http://localhost:5000` 即可查看数据仪表盘。

---

## 模块一：Requests 爬虫（requests_douban）

基于 `requests` + `BeautifulSoup` 的单进程/多线程爬虫，适合快速采集、调试和自定义采集流程。

### CLI 命令总览

```powershell
python -m requests_douban.cli [参数]
```

### 爬取模式

`--mode` 支持三种模式：

| 模式 | 说明 |
|---|---|
| `top250`（默认） | 自动构建豆瓣 Top250 分页 URL（`?start=0,25,50...`） |
| `urls` | 指定一个或多个自定义 URL，支持自动分页展开 |
| `import` | 从已有的 `douban_items.json` / `.csv` 加载数据，可选存入 MySQL |

### 完整参数表

#### 爬取目标控制

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `--mode` | `top250` / `urls` / `import` | `top250` | 爬取模式 |
| `--url` | 文本（可重复） | 无 | 自定义 URL（`--mode urls` 必填） |
| `--max-pages` | int | `1` | Top250 分页数或 URL 分页数 |
| `--output-dir` | 路径 | `data/crawler` | JSON / CSV / images 输出目录 |
| `--page-param` | 文本 | `start` | 自定义 URL 分页参数名 |
| `--page-size` | int | `25` | 分页步长 |

#### 数据采集范围

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `--comment-limit` | int | `20` | 每部电影短评采集条数，设为 `0` 跳过 |
| `--no-details` | 开关 | 不启用 | 跳过详情页（仅采集列表信息） |
| `--no-images` | 开关 | 不启用 | 跳过封面图下载 |

#### 并发控制

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `--detail-workers` | int | `1` | 详情页+短评并发线程数 |
| `--image-workers` | int | `1` | 图片下载并发线程数 |
| `--fast` | 开关 | 不启用 | 快速模式预设（4 detail workers + 6 image workers + 0.5~1.5s 延迟） |

> **注意**：Selenium 模式下详情页始终顺序执行（共享浏览器实例）。

#### 反爬与网络

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `--cookie` | 文本 | 无 | 豆瓣 Cookie 字符串 |
| `--proxy` | 文本（可重复） | 无 | 代理 URL，支持重复以轮换代理池 |
| `--delay-min` | float | `1.2` | 请求最小间隔（秒） |
| `--delay-max` | float | `3.5` | 请求最大间隔（秒） |

#### Selenium 渲染

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `--use-selenium` | 开关 | 不启用 | 启用 Selenium 三级降级渲染 |
| `--show-browser` | 开关 | 不启用 | 显示 Chrome 窗口（调试用） |
| `--driver-path` | 路径 | 无 | chromedriver.exe 路径 |

#### MySQL 存储

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `--save-mysql` | 开关 | 不启用 | 采集/导入后写入 MySQL 并导出备份 |

> MySQL 连接参数（host/port/user/password/database）通过 [`database_service`](#模块三mysql-存储database_service) 模块管理，默认连接 `localhost:3306`，用户名 `root`，密码 `123456`。如需自定义，请直接调用 Python API。

### 常用示例

#### Top250 采集

```powershell
# 采集第 1 页（默认行为），含详情+短评+图片
python -m requests_douban.cli

# 采集前 5 页（共 125 部）
python -m requests_douban.cli --mode top250 --max-pages 5

# 快速模式：4线程详情+6线程图片
python -m requests_douban.cli --mode top250 --max-pages 3 --fast

# 只采集列表页，不进详情、不下图
python -m requests_douban.cli --mode top250 --max-pages 1 --no-details --no-images

# 每部电影采集 50 条短评
python -m requests_douban.cli --mode top250 --max-pages 2 --comment-limit 50
```

#### 自定义 URL 采集

```powershell
# 单个页面
python -m requests_douban.cli --mode urls --url "https://movie.douban.com/top250"

# 多个页面
python -m requests_douban.cli --mode urls `
    --url "https://movie.douban.com/subject/1292052/" `
    --url "https://movie.douban.com/subject/1291561/"

# 搜索结果分页采集
python -m requests_douban.cli --mode urls --max-pages 5 `
    --url "https://search.douban.com/movie/subject_search?search_text=宫崎骏"
```

#### Cookie 与代理

```powershell
# Cookie 登录态
python -m requests_douban.cli --cookie "bid=xxx; dbcl2=xxx"

# 单代理
python -m requests_douban.cli --proxy "http://127.0.0.1:7890"

# 代理池轮换
python -m requests_douban.cli --proxy "http://127.0.0.1:7890" --proxy "http://127.0.0.1:7891"
```

#### Selenium 降级

```powershell
# 普通请求被拦截时自动用 Selenium 重试
python -m requests_douban.cli --mode top250 --max-pages 1 --use-selenium

# 显示浏览器窗口（调试）
python -m requests_douban.cli --mode top250 --max-pages 1 --use-selenium --show-browser

# 指定 chromedriver
python -m requests_douban.cli --mode top250 --max-pages 1 --use-selenium --driver-path "D:\chromedriver.exe"
```

#### MySQL 存储

```powershell
# 采集后存入 MySQL
python -m requests_douban.cli --mode top250 --max-pages 1 --save-mysql

# 从已有 JSON 导入 MySQL（会先清空表再导入）
python -m requests_douban.cli --mode import --save-mysql

# 完整流程：采集→清洗→存MySQL
python -m requests_douban.cli --mode top250 --max-pages 3 --comment-limit 30 --fast --save-mysql
```

#### 自定义延迟

```powershell
# 保守延迟（更礼貌）
python -m requests_douban.cli --mode top250 --max-pages 2 --delay-min 3.0 --delay-max 6.0

# 快速采集
python -m requests_douban.cli --mode top250 --max-pages 1 --delay-min 0.5 --delay-max 1.0
```

---

## 模块二：Scrapy 爬虫（scrapy_douban）

基于 Scrapy 异步框架的爬虫，利用引擎级并发调度，适合大规模、高效率采集。**复用** `requests_douban` 的解析器、清洗器和 Selenium 降级链路。

### 启动方式

**方式一：便捷脚本（推荐）**

```powershell
python run_scrapy_spider.py [参数]
```

| 参数 | 说明 |
|---|---|
| `--spider` | `top250`（默认）或 `custom` |
| `--max-pages` | 分页数 |
| `--comment-limit` | 短评采集数 |
| `--no-details` | 跳过详情页 |
| `--no-images` | 跳过图片 |
| `--urls` | 自定义 URL（逗号分隔，配合 `--spider custom`） |
| `--output-dir` | 输出目录 |
| `--cookie` | Cookie 字符串 |
| `--proxy` | 代理 URL |

**方式二：标准 Scrapy 命令**

```powershell
cd scrapy_douban
scrapy crawl top250 -a max_pages=10 -a comment_limit=20
scrapy crawl custom -a urls="https://movie.douban.com/top250?start=0" -a max_pages=3
```

### Spider 说明

| Spider | 说明 |
|---|---|
| `top250` | Top250 Spider：异步采集列表页，详情/短评委托给 `requests_douban.DoubanCrawler`（含桌面→移动→Selenium 三级降级） |
| `custom` | 自定义 URL Spider：支持 `{page}` / `{start}` 模板变量和 `start`/`page` 查询参数自动分页 |

### 中间件与管道

**下载中间件**（按优先级排序）：

| 中间件 | 功能 |
|---|---|
| `RandomUserAgentMiddleware` | 随机 User-Agent 轮换，支持 Sec-CH-UA 头 |
| `ProxyMiddleware` | 代理注入 |
| `DoubanCookieMiddleware` | Cookie 自动注入 |
| `AntiSpiderRetryMiddleware` | 反爬检测 + 自动重试（检测封禁标题/登录跳转/403/429） |

**Item Pipeline**：

| 管道 | 功能 |
|---|---|
| `CleaningPipeline` | 调用 `requests_douban.cleaner.clean_items()` 标准化数据 |
| `ImageDownloadPipeline` | 多线程图片下载 |
| `ExportPipeline` | JSON + CSV 双格式导出 |

### Scrapy 常用示例

```powershell
# Top250 快速采集（2页）
python run_scrapy_spider.py --spider top250 --max-pages 2

# 跳过详情页（仅列表）
python run_scrapy_spider.py --spider top250 --max-pages 1 --no-details --no-images

# 自定义 URL
python run_scrapy_spider.py --spider custom --urls "https://movie.douban.com/top250" --max-pages 3

# 带 Cookie 和代理
python run_scrapy_spider.py --spider top250 --max-pages 1 --cookie "bid=xxx" --proxy "http://127.0.0.1:7890"
```

---

## 模块三：MySQL 存储（database_service）

提供独立的 MySQL 持久化能力，支持自动建库建表、增量去重导入、备份导出。

### Python API

```python
from database_service import save_to_mysql, export_backup
from database_service.config import MySQLConfig

# 写入 MySQL（自动建库建表 + 去重 + 导出备份）
items = [
    {
        "title": "肖申克的救赎",
        "url": "https://movie.douban.com/subject/1292052/",
        "rating": 9.7,
        "runtime": 142,
        "short_comments": "用户：A | 评分：力荐 | 时间：2024-01 | 有用：99 | 评论：经典\n...",
        # ... 其他字段
    }
]

inserted = save_to_mysql(
    items,
    host="localhost",
    port=3306,
    user="root",
    password="123456",
    database="douban",
    backup_dir="data/database/backup",
    recreate=False,  # True = 先删表重建（全量导入），False = 增量去重
)
print(f"新增 {inserted} 条记录")

# 单独导出备份
cfg = MySQLConfig(host="localhost", user="root", password="123456", database="douban")
json_path, movies_csv, comments_csv = export_backup(cfg)
```

### 数据库表结构

#### movies 表（电影主表）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INT AUTO_INCREMENT | 主键 |
| `rank` | INT | Top250 排名 |
| `title` | VARCHAR(255) | 完整标题 |
| `title_cn` | VARCHAR(255) | 中文标题 |
| `title_en` | VARCHAR(255) | 英文/其他语言标题 |
| `url` | VARCHAR(512) UNIQUE | 详情页 URL（去重依据） |
| `rating` | DECIMAL(3,1) | 评分 |
| `comment_count` | INT | 评价人数 |
| `summary` | TEXT | 剧情简介 |
| `director` / `screenwriter` / `actors` | VARCHAR/TEXT | 导演 / 编剧 / 主演 |
| `genres` / `country` / `language` | VARCHAR(255) | 类型 / 国家 / 语言 |
| `release_date` | VARCHAR(255) | 上映日期 |
| `runtime` | INT | 片长（分钟） |
| `imdb` | VARCHAR(50) | IMDb 编号（ttXXXXXX） |
| `detail_error` | TEXT | 详情页采集错误信息 |
| `created_at` | TIMESTAMP | 创建时间 |

#### comments 表（短评从表）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INT AUTO_INCREMENT | 主键 |
| `movie_id` | INT NOT NULL | 外键 → movies(id)，`ON DELETE CASCADE` |
| `user` | VARCHAR(255) | 评论用户 |
| `rating` | VARCHAR(50) | 用户评分（力荐/推荐/还行/较差/很差） |
| `comment_time` | VARCHAR(100) | 评论时间 |
| `helpful` | INT | 有用数 |
| `comment` | TEXT | 评论内容 |
| `created_at` | TIMESTAMP | 创建时间 |

唯一约束：`UNIQUE KEY uk_movie_user_time (movie_id, user, comment_time, comment(255))`

### 数据去重与增量导入

- **增量模式**（`recreate=False`，默认）：先检查 URL 是否存在，已存在则跳过。适用于逐次追加数据
- **全量导入**（`recreate=True`）：先 `DROP TABLE` 再重建，全部重新插入。适用于从 JSON 批量重建数据库

通过 `--mode import --save-mysql` 调用时，自动使用全量导入模式。

### 备份导出格式

| 文件 | 格式 | 内容 |
|---|---|---|
| `douban_movies.json` | JSON 嵌套 | 每条电影记录内嵌 `comments` 数组 |
| `douban_movies.csv` | CSV | 电影字段（不含评论） |
| `douban_comments.csv` | CSV | 评论记录（含 movie_id + 电影标题） |

---

## 模块四：数据分析与 Web 仪表盘（analysis）

### 数据分析脚本

```powershell
python analysis/douban_analysis.py
```

功能：
- **数据清洗**：缺失值处理、类型转换、去重
- **统计分析**：高分 Top10、导演/类型分布、评分与评论数相关性、短评情感倾向
- **可视化输出**（输出到 `analysis/output/`）：
  - 评分分布直方图
  - 电影类型饼图
  - 评分 vs 评价人数散点图
  - 短评词云
  - 上映年份时间趋势图
  - 国家/地区分布图
  - …等 10+ 张图表

支持 `matplotlib` + `seaborn` 和 `plotly` 双引擎。自动检测系统中文黑体/微软雅黑字体。

### Web 仪表盘

```powershell
# 默认 localhost:5000
python analysis/web_server.py

# 自定义端口和地址
python analysis/web_server.py --port 8080 --host 0.0.0.0
```

启动后浏览器访问 `http://localhost:5000`，提供三大功能分区：

| 功能区 | 说明 |
|---|---|
| 📊 **数据仪表盘** | 16+ 交互式 Plotly 图表（评分分布、类型饼图、国家热力图、年代趋势等），支持类型/国家/年代联动筛选 |
| 🕷️ **爬虫控制** | 在线启停 requests 爬虫，实时查看日志流，配置 Top250 / URL / Import 参数 |
| 🗄️ **数据库管理** | MySQL 连接状态监控、movies / comments 表统计、一键备份导出 |

> 首次启动建议先运行 `python analysis/download_deps.py` 下载前端依赖（jQuery / DataTables），否则需联网加载 CDN 资源。

---

## 辅助工具

### 爬虫基准测试（bench_compare.py）

对比 Scrapy 和 Requests 两种引擎的性能差异：

```powershell
# 双引擎各跑 1 页 Top250
python bench_compare.py --pages 1

# 只跑 requests
python bench_compare.py --pages 2 --requests-only

# 只跑 Scrapy
python bench_compare.py --pages 2 --scrapy-only

# 跳过详情页（加速）
python bench_compare.py --pages 1 --no-details
```

输出内容包括：
- 耗时对比（总时间 + 每部电影平均时间）
- 代码复杂度对比（各模块源码行数）
- 架构对比图（数据流对比）

### 数据验证（_check_data.py）

```powershell
python _check_data.py
```

快速检查指定 JSON 文件的数据质量：总记录数、有导演/短评的记录数、详情页错误统计。

---

## 数据文件格式

### 爬虫输出（data/crawler/）

#### douban_items.json 字段

```json
[
  {
    "title": "肖申克的救赎 The Shawshank Redemption",
    "url": "https://movie.douban.com/subject/1292052/",
    "rank": 1,
    "title_cn": "肖申克的救赎",
    "title_en": "The Shawshank Redemption",
    "rating": 9.7,
    "comment_count": 3282402,
    "summary": "有的人的羽翼是如此光辉...",
    "image_url": "https://img2.doubanio.com/view/photo/s_ratio_poster/public/p480747492.webp",
    "source_page": "https://movie.douban.com/top250?start=0",
    "image_file": "data/crawler/images/肖申克的救赎.webp",
    "director": "弗兰克·德拉邦特",
    "screenwriter": "弗兰克·德拉邦特 / 斯蒂芬·金",
    "actors": "蒂姆·罗宾斯 / 摩根·弗里曼 / ...",
    "genres": "剧情 / 犯罪",
    "country": "美国",
    "language": "英语",
    "release_date": "1994-09-23(美国)",
    "runtime": 142,
    "imdb": "tt0111161",
    "short_comments": "用户：A | 评分：力荐 | 时间：2024-01-15 | 有用：99 | 评论：经典...\n...",
    "detail_error": ""
  }
]
```

#### 字段类型说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `rank` | int | Top250 排名（非 Top250 页为 null） |
| `title` | str | 完整标题 |
| `title_cn` / `title_en` | str | 拆分的中/英文标题 |
| `rating` | float | 评分（已清洗为浮点数） |
| `comment_count` | int | 评价人数（已清洗为整数） |
| `runtime` | int | 片长，单位：分钟 |
| `short_comments` | str | 多条短评 `\n` 分隔，格式：`用户：x \| 评分：x \| 时间：x \| 有用：x \| 评论：x` |

### MySQL 备份（data/database/backup/）

`douban_movies.json` 与爬虫格式一致，额外包含解析后的 `comments` 数组：

```json
[
  {
    "id": 1,
    "title": "肖申克的救赎",
    "comments": [
      {"user": "A", "rating": "力荐", "comment_time": "2024-01-15", "helpful": 99, "comment": "经典"}
    ]
  }
]
```

`douban_movies.csv` 和 `douban_comments.csv` 均为 UTF-8 BOM 编码，Excel 可直接打开。

---

## 爬虫数据流全景

```
┌──────────────────────────────────────────────────────┐
│                    CLI / Python API                   │
└──────────┬──────────────┬──────────────┬─────────────┘
           │              │              │
    ┌──────▼──────┐ ┌─────▼──────┐ ┌────▼──────────┐
    │ requests    │ │  Scrapy    │ │  import mode  │
    │ crawler     │ │  spider    │ │  (from JSON)  │
    └──────┬──────┘ └─────┬──────┘ └────┬──────────┘
           │              │              │
           │     ┌────────┘              │
           ▼     ▼                       ▼
    ┌──────────────────────────────────────────┐
    │           cleaner.clean_items()           │
    │  (NBSP→space, rating→float, runtime→int) │
    └──────────────────┬───────────────────────┘
                       │
           ┌───────────┼───────────┐
           ▼           ▼           ▼
    ┌──────────┐ ┌──────────┐ ┌──────────────┐
    │ JSON/CSV │ │  MySQL   │ │ image files  │
    │ (crawler)│ │(database)│ │ (images/)    │
    └──────────┘ └────┬─────┘ └──────────────┘
                      │
              ┌───────▼───────┐
              │ export_backup │
              │ JSON + CSV×2  │
              └───────┬───────┘
                      │
              ┌───────▼───────────────────┐
              │  analysis / web_server    │
              │  (Flask + Plotly 仪表盘)  │
              └───────────────────────────┘
```

数据采集 → 清洗标准化 → 多路输出（JSON/CSV/MySQL）→ 备份导出 → 分析可视化，形成完整数据管线。

---

## 合规提醒

1. **控制频率**：默认请求间隔 1.2~3.5 秒，请勿大幅下调。对豆瓣服务器保持礼貌
2. **仅采集公开数据**：不绕过登录验证、验证码或访问权限控制
3. **遵守 robots.txt**：豆瓣 `robots.txt` 对爬虫有约束，请遵守相关规则
4. **及时停止**：若返回验证码或"访问过于频繁"提示，立即降低频率或暂停
5. **合法使用**：采集数据仅用于个人学习和研究，不得用于商业用途
6. **Selenium 谨慎使用**：浏览器渲染开销较大，仅在必要时启用
