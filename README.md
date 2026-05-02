# 豆瓣电影数据采集与存储项目

豆瓣电影数据爬虫（支持 Top250 / 自定义 URL 采集）+ MySQL 持久化存储与备份导出工具。

## 目录

- [项目概述](#项目概述)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [模块 A：数据采集（member_a_douban）](#模块-a数据采集member_a_douban)
  - [CLI 命令总览](#cli-命令总览)
  - [爬取模式](#爬取模式)
  - [参数详解](#参数详解)
  - [常用示例](#常用示例)
- [模块 B：MySQL 存储（member_b_douban）](#模块-bmysql-存储member_b_douban)
  - [Python API](#python-api)
  - [数据库表结构](#数据库表结构)
  - [备份导出格式](#备份导出格式)
- [数据文件格式](#数据文件格式)
- [合规提醒](#合规提醒)

## 项目概述

本项目实现从豆瓣电影页面采集电影数据（标题、评分、详情、短评、封面图等），并提供以下能力：

- **数据采集**：基于 `requests` 的爬虫，支持随机 User-Agent、随机延迟、Cookie 注入、代理配置、自动重试等反爬策略
- **动态页面兜底**：可选 Selenium 渲染器，在普通请求被拦截时自动降级为浏览器渲染
- **图片下载**：自动下载电影封面图，按 URL 哈希命名避免重复
- **MySQL 持久化**：自动建库建表，双表存储（电影主表 + 短评从表），按 URL 去重
- **备份导出**：从 MySQL 导出为嵌套 JSON 和两张 CSV 文件

## 项目结构

```
F:\douban\
├── member_a_douban/          # 采集模块（成员A）
│   ├── __init__.py           # 包入口，暴露版本号
│   ├── cli.py                # 命令行入口，定义所有参数和模式
│   ├── crawler.py            # 爬虫工作流编排
│   ├── config.py             # 爬虫配置数据类（CrawlConfig）
│   ├── http_client.py        # requests 客户端（重试/Cookie/UA轮换）
│   ├── parser.py             # HTML 解析（BeautifulSoup）
│   ├── image_downloader.py   # 图片下载
│   ├── selenium_renderer.py  # Selenium 动态渲染器
│   └── anti_spider.py        # 反爬辅助工具
│
├── member_b_douban/          # 存储模块（成员B）
│   ├── __init__.py           # 统一入口（save_to_mysql / export_backup）
│   ├── config.py             # MySQL 连接配置数据类
│   ├── database.py           # 数据库初始化与连接管理
│   ├── repository.py         # 数据访问层（插入/查询）
│   └── exporter.py           # 备份导出（JSON + CSV）
│
├── data/                     # 数据输出目录（已 gitignore）
│   ├── member_a/             # 爬虫输出（JSON / CSV / images）
│   └── member_b/backup/      # MySQL 备份导出
│
├── requirements.txt          # Python 依赖
└── .gitignore
```

## 快速开始

### 1. 安装依赖

```powershell
pip install -r requirements.txt
```

依赖包说明：

| 包名 | 用途 | 可选 |
|---|---|---|
| beautifulsoup4 | HTML 解析 | 必选 |
| lxml | HTML 解析加速 | 必选 |
| requests | HTTP 客户端 | 必选 |
| selenium | 动态页面渲染 | 可选（不使用 `--use-selenium` 可跳过） |
| pymysql | MySQL 连接 | 可选（不使用 `--save-mysql` 可跳过） |
| cryptography | MySQL 认证 | 可选（不使用 `--save-mysql` 可跳过） |

### 2. 快速体验

```powershell
# 采集 Top250 第一页，输出 JSON / CSV
python -m member_a_douban.cli --mode top250 --max-pages 1

# 采集 Top250 前 2 页，并存入 MySQL
python -m member_a_douban.cli --mode top250 --max-pages 2 --save-mysql
```

---

## 模块 A：数据采集（member_a_douban）

### CLI 命令总览

```powershell
python -m member_a_douban.cli [参数]
```

### 爬取模式

`--mode` 参数支持三种模式：

| 模式 | 说明 |
|---|---|
| `top250`（默认） | 自动构造豆瓣 Top250 分页 URL，从 `https://movie.douban.com/top250` 开始采集 |
| `urls` | 采集用户通过 `--url` 指定的一个或多个自定义链接 |
| `import` | 从之前爬取的 `douban_items.json` 重新生成 CSV，无需网络请求 |

### 参数详解

#### 爬取目标

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `--mode` | `top250` / `urls` / `import` | `top250` | 控制爬取模式 |
| `--url` | 文本（可多次使用） | 无 | 自定义豆瓣页面 URL，用于 `--mode urls` |
| `--max-pages` | 整数 | `1` | 最大爬取页数。`top250` 模式每页 25 条，`urls` 模式限制 URL 数量 |
| `--output-dir` | 路径 | `data/member_a` | 输出目录 |

#### 反爬与网络

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `--cookie` | 文本 | 无 | 豆瓣 Cookie 字符串，用于访问需要登录的页面（如个人收藏） |
| `--delay-min` | 浮点数 | `1.2` | 请求间最小延迟（秒） |
| `--delay-max` | 浮点数 | `3.5` | 请求间最大延迟（秒） |

#### Selenium 动态渲染

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `--use-selenium` | 开关 | 不启用 | 启用 Selenium 兜底：普通请求被拦截时自动用浏览器渲染 |
| `--show-browser` | 开关 | 不启用 | 显示 Chrome 浏览器窗口（默认无头模式） |
| `--driver-path` | 路径 | 无 | ChromeDriver 可执行文件路径，如果不在 PATH 中需指定 |

#### 数据采集范围

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `--no-images` | 开关 | 下载图片 | 跳过封面图下载 |
| `--no-details` | 开关 | 采集详情 | 跳过电影详情页（只采集列表数据） |
| `--comment-limit` | 整数 | `3` | 每部电影采集的短评条数。设为 `0` 跳过短评 |

#### MySQL 存储

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `--save-mysql` | 开关 | 不存储 | 采集完成后将数据写入 MySQL |
| `--mysql-host` | 文本 | `localhost` | MySQL 主机 |
| `--mysql-port` | 整数 | `3306` | MySQL 端口 |
| `--mysql-user` | 文本 | `root` | MySQL 用户名 |
| `--mysql-password` | 文本 | `123456` | MySQL 密码 |
| `--mysql-database` | 文本 | `douban` | MySQL 数据库名 |
| `--mysql-backup-dir` | 路径 | `data/member_b/backup` | MySQL 备份导出目录 |

### 常用示例

#### 采集 Top250

```powershell
# 采集第 1 页（默认行为）
python -m member_a_douban.cli

# 采集前 5 页（共 125 部电影）
python -m member_a_douban.cli --mode top250 --max-pages 5

# 只采集列表数据，不进入详情页，不下载图片
python -m member_a_douban.cli --mode top250 --max-pages 1 --no-details --no-images
```

#### 采集自定义页面

```powershell
# 采集单个自定义页面
python -m member_a_douban.cli --mode urls --url "https://movie.douban.com/subject/1292052/"

# 采集多个页面
python -m member_a_douban.cli --mode urls `
    --url "https://movie.douban.com/subject/1292052/" `
    --url "https://movie.douban.com/subject/1291561/"

# 采集搜索结果页
python -m member_a_douban.cli --mode urls --max-pages 2 `
    --url "https://search.douban.com/movie/subject_search?search_text=宫崎骏"
```

#### 使用 Cookie

```powershell
# 传入 Cookie 访问需登录的页面
python -m member_a_douban.cli --mode top250 --max-pages 1 `
    --cookie "bid=xxxxxxxxxx; dbcl2=xxxxxxxxxx"
```

Cookie 获取方式：在浏览器中登录豆瓣后，按 F12 → 网络 → 复制任意请求头中的 Cookie 字符串。

#### 使用 Selenium 兜底

```powershell
# 普通请求被拦截时自动用 Selenium 重试
python -m member_a_douban.cli --mode top250 --max-pages 1 --use-selenium

# 显示浏览器窗口（方便观察）
python -m member_a_douban.cli --mode top250 --max-pages 1 --use-selenium --show-browser

# 指定 ChromeDriver 路径
python -m member_a_douban.cli --mode top250 --max-pages 1 --use-selenium `
    --driver-path "D:\tools\chromedriver.exe"
```

#### 采集并保存到 MySQL

```powershell
# 采集 Top250 第 1 页并存入 MySQL（自动建库建表）
python -m member_a_douban.cli --mode top250 --max-pages 1 --save-mysql

# 指定 MySQL 连接参数
python -m member_a_douban.cli --mode top250 --max-pages 5 --save-mysql `
    --mysql-host 127.0.0.1 --mysql-port 3306 `
    --mysql-user root --mysql-password mypass --mysql-database douban_movies

# 不爬取短评，只存电影主信息
python -m member_a_douban.cli --mode top250 --max-pages 3 --comment-limit 0 --save-mysql
```

#### 从已有 JSON 重新生成 CSV（import 模式）

```powershell
# 之前已爬取过，重新生成 CSV
python -m member_a_douban.cli --mode import --output-dir data/member_a
```

此模式会读取 `data/member_a/douban_items.json`，将其重新导出为 `douban_items.csv`。适用于修改字段后需要重新生成 CSV 的场景。

#### 自定义延迟控制

```powershell
# 降低爬取频率（更礼貌）
python -m member_a_douban.cli --mode top250 --max-pages 2 `
    --delay-min 3.0 --delay-max 6.0

# 快速采集（高频，请谨慎使用）
python -m member_a_douban.cli --mode top250 --max-pages 1 `
    --delay-min 0.5 --delay-max 1.0
```

#### 组合参数（完整示例）

```powershell
# 采集 Top250 前 3 页，进详情页，下载图片，每条 5 条短评，存入 MySQL
python -m member_a_douban.cli `
    --mode top250 --max-pages 3 `
    --comment-limit 5 `
    --delay-min 2.0 --delay-max 4.0 `
    --save-mysql `
    --mysql-host 127.0.0.1 --mysql-user root --mysql-password 123456 --mysql-database douban

# 采集自定义电影列表，启用 Selenium，保存到 MySQL，指定备份目录
python -m member_a_douban.cli `
    --mode urls --url "https://movie.douban.com/top250" `
    --max-pages 2 --use-selenium `
    --comment-limit 10 `
    --save-mysql --mysql-backup-dir "D:\backups\douban"
```

---

## 模块 B：MySQL 存储（member_b_douban）

本模块提供独立的 MySQL 存储能力，可通过 Python API 直接调用，也可通过模块 A 的 `--save-mysql` 参数间接使用。

### Python API

#### 保存数据到 MySQL

```python
from member_b_douban import save_to_mysql

# 构造符合 DoubanItem.to_dict() 格式的数据
items = [
    {
        "title": "肖申克的救赎",
        "url": "https://movie.douban.com/subject/1292052/",
        "rating": "9.7",
        "comment_count": "3150000",
        "summary": "有的人的羽翼是如此光辉...",
        "director": "弗兰克·德拉邦特",
        "actors": "蒂姆·罗宾斯 / 摩根·弗里曼",
        "genres": "剧情 / 犯罪",
        "short_comments": "用户：A | 评分：力荐 | 时间：2024-01 | 评论：经典\n用户：B | 评论：好看",
        # ... 其他字段
    }
]

# 写入 MySQL（自动建库建表 + 去重 + 导出备份）
inserted = save_to_mysql(
    items,
    host="localhost",
    port=3306,
    user="root",
    password="123456",
    database="douban",
    backup_dir="data/member_b/backup",
)
print(f"新增 {inserted} 条记录")
```

#### 从 MySQL 导出备份

```python
from member_b_douban import export_backup
from member_b_douban.config import MySQLConfig

cfg = MySQLConfig(
    host="localhost",
    user="root",
    password="123456",
    database="douban",
    backup_dir="data/member_b/backup",
)

json_path, movies_csv, comments_csv = export_backup(cfg)
print(f"JSON: {json_path}")
print(f"电影 CSV: {movies_csv}")
print(f"评论 CSV: {comments_csv}")
```

### 数据库表结构

#### movies 表（电影主表）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INT AUTO_INCREMENT | 主键 |
| `title` | VARCHAR(255) | 电影标题 |
| `url` | VARCHAR(512) | 详情页 URL（唯一键，用于去重） |
| `rating` | VARCHAR(10) | 评分 |
| `comment_count` | VARCHAR(20) | 评价人数 |
| `summary` | TEXT | 剧情简介 |
| `image_url` | VARCHAR(512) | 封面图 URL |
| `source_page` | VARCHAR(512) | 来源列表页 |
| `image_file` | VARCHAR(512) | 封面图本地路径 |
| `director` | VARCHAR(255) | 导演 |
| `screenwriter` | VARCHAR(255) | 编剧 |
| `actors` | TEXT | 主演 |
| `genres` | VARCHAR(255) | 类型 |
| `country` | VARCHAR(255) | 制片国家/地区 |
| `language` | VARCHAR(255) | 语言 |
| `release_date` | VARCHAR(255) | 上映日期 |
| `runtime` | VARCHAR(100) | 片长 |
| `imdb` | VARCHAR(50) | IMDb 编号 |
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
| `helpful` | VARCHAR(20) | 有用数 |
| `comment` | TEXT | 评论内容 |
| `created_at` | TIMESTAMP | 创建时间 |

### 备份导出格式

执行 `--save-mysql` 或调用 `export_backup()` 后，会在备份目录生成三个文件：

| 文件 | 格式 | 内容 |
|---|---|---|
| `douban_movies.json` | JSON 嵌套 | 每条电影记录内嵌 `comments` 数组 |
| `douban_movies.csv` | CSV | 电影字段（不含评论） |
| `douban_comments.csv` | CSV | 评论记录（含 `movie_id`、对应电影标题） |

---

## 数据文件格式

### 爬虫输出（data/member_a/）

#### douban_items.json 字段说明

```json
[
  {
    "title": "肖申克的救赎",
    "url": "https://movie.douban.com/subject/1292052/",
    "rating": "9.7",
    "comment_count": "3150000",
    "summary": "有的人的羽翼是如此光辉...",
    "image_url": "https://img2.doubanio.com/...",
    "source_page": "https://movie.douban.com/top250",
    "image_file": "data/member_a/images/abc123.jpg",
    "director": "弗兰克·德拉邦特",
    "screenwriter": "弗兰克·德拉邦特 / 斯蒂芬·金",
    "actors": "蒂姆·罗宾斯 / 摩根·弗里曼",
    "genres": "剧情 / 犯罪",
    "country": "美国",
    "language": "英语",
    "release_date": "1994-09-23(美国)",
    "runtime": "142分钟",
    "imdb": "tt0111161",
    "short_comments": "用户：A | 评分：力荐 | 时间：2024-01 | 有用：123 | 评论：经典...",
    "detail_error": ""
  }
]
```

#### douban_items.csv

与 JSON 字段相同，使用 UTF-8 BOM 编码（Excel 可直接打开），`short_comments` 多行以 `\n` 分隔。

### MySQL 备份输出（data/member_b/backup/）

#### douban_movies.json

与爬虫 JSON 格式一致，但每条电影记录额外包含 `comments` 数组（已解析为结构化字段）：

```json
[
  {
    "id": 1,
    "title": "肖申克的救赎",
    "comments": [
      {
        "user": "A",
        "rating": "力荐",
        "comment_time": "2024-01-15",
        "helpful": "123",
        "comment": "经典"
      }
    ]
  }
]
```

#### douban_movies.csv / douban_comments.csv

两张拆分 CSV，电影表和评论表分别导出，UTF-8 BOM 编码。

---

## 合规提醒

1. **控制频率**：请保持合理的请求间隔（默认 `1.2–3.5` 秒），避免对豆瓣服务器造成压力
2. **仅采集公开数据**：不要绕过登录验证、验证码或权限控制
3. **尊重 robots.txt**：豆瓣的 `robots.txt` 对爬虫有约束，请遵守相关规则
4. **及时停止**：若豆瓣返回验证码或"访问过于频繁"提示，应降低频率或暂停采集
5. **合法使用**：采集的数据请仅用于个人学习研究，勿用于商业用途
