# 豆瓣采集项目 - 成员B模块

本模块为成员A爬虫提供 **MySQL 数据持久化** 支持，同时实现数据存在性校验（跳过已爬取内容）和备份导出功能。

## 功能范围

- **MySQL 双表存储**：自动创建 `movies` 主表 + `comments` 短评表，通过外键关联，`ON DELETE CASCADE`
- **数据去重**：按 `url` 唯一键防重复插入
- **跳过已爬取**：与 `requests_douban` 集成，`--skip-crawled` 参数可在数据已存在时跳过爬取，直接从 MySQL 加载导出
- **备份导出**：从 MySQL 读取数据，生成嵌套 JSON + 两张 CSV（movies + comments 分开）作为数据备份

## 模块结构

```
database_service/
├── __init__.py      统一入口：save_to_mysql / has_existing_data / load_and_export
├── config.py        MySQLConfig 数据类（连接参数 + 备份目录）
├── database.py      建库建表（movies + comments 两张 InnoDB 表）
├── repository.py    DAO 层：插入数据、查询计数/URL存在性
├── exporter.py      从 MySQL 导出 JSON / CSV 备份文件
└── README.md        本文件
```

## 环境要求

- Python 3.10+
- MySQL 8.0+ 服务端已安装并运行
- 依赖包：`pymysql` + `cryptography`

```powershell
pip install pymysql cryptography
```

或使用项目根目录的 `requirements.txt` 统一安装：

```powershell
pip install -r requirements.txt
```

## 数据库表结构

### movies（主表）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INT AUTO_INCREMENT | 主键 |
| title | VARCHAR(255) | 电影标题 |
| url | VARCHAR(512) UNIQUE | 详情页 URL（去重依据） |
| rating | VARCHAR(10) | 评分 |
| comment_count | VARCHAR(20) | 评价人数 |
| summary | TEXT | 剧情简介 |
| image_url / image_file | VARCHAR(512) | 封面图 URL / 本地路径 |
| director / screenwriter / actors | VARCHAR/TEXT | 导演 / 编剧 / 演员 |
| genres / country / language | VARCHAR(255) | 类型 / 国家 / 语言 |
| release_date / runtime | VARCHAR(255) | 上映日期 / 片长 |
| imdb | VARCHAR(50) | IMDb 编号 |
| detail_error | TEXT | 详情页采集错误信息 |
| created_at | TIMESTAMP | 记录创建时间 |

### comments（从表）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INT AUTO_INCREMENT | 主键 |
| movie_id | INT NOT NULL | 外键 → movies(id) |
| raw_comment | TEXT NOT NULL | 单条短评原文 |
| created_at | TIMESTAMP | 记录创建时间 |

外键约束：`FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE`

## 使用方式

### 1. 通过 requests_douban 的 CLI 调用（推荐）

直接使用成员A的命令行入口，传入 `--save-mysql` 即可：

```powershell
# 爬取 Top250 第1页并存入 MySQL
python -m requests_douban.cli --mode top250 --max-pages 1 --save-mysql

# 启用跳过已爬取：如果 MySQL 已有数据则跳过爬取
python -m requests_douban.cli --mode top250 --max-pages 1 --save-mysql --skip-crawled

# 自定义 MySQL 连接参数
python -m requests_douban.cli --mode top250 --max-pages 1 --save-mysql `
    --mysql-host 127.0.0.1 --mysql-port 3306 `
    --mysql-user root --mysql-password 123456 --mysql-database douban
```

### 2. 直接导入 Python 代码

```python
from database_service import save_to_mysql, has_existing_data, load_and_export

# 检查 MySQL 是否已有数据
if not has_existing_data(host="localhost", database="douban"):
    # 爬取数据...
    items = [...]  # list[dict]
    save_to_mysql(items)

# 从 MySQL 加载并导出文件
json_path, csv_path, bk_json, bk_csv, bk_cmts = load_and_export(
    output_dir="data/member_a",
)
```

## 输出文件

运行 `--save-mysql` 后，默认在以下位置生成备份文件：

### MySQL 备份（data/member_b/backup/）

| 文件 | 格式 | 内容 |
|---|---|---|
| `douban_movies.json` | JSON 嵌套 | 每条电影记录内嵌 `comments` 数组 |
| `douban_movies.csv` | CSV | 电影字段（不含评论） |
| `douban_comments.csv` | CSV | 评论记录（含 movie_id、电影标题） |

### 成员A输出（data/member_a/）

| 文件 | 格式 | 内容 |
|---|---|---|
| `douban_items.json` | JSON | 与爬虫直接输出格式一致 |
| `douban_items.csv` | CSV | 与爬虫直接输出格式一致 |

当 `--skip-crawled` 启用时，这些文件改为从 MySQL 加载数据生成，而非爬虫实时输出。

## 与成员A的集成

成员A的 `cli.py` 通过参数方式与本模块对接：

1. `--save-mysql` — 爬取完成后调用 `save_to_mysql()` 写入 MySQL 并导出备份
2. `--skip-crawled` — 爬取前调用 `has_existing_data()` 检查，数据已存在则调用 `load_and_export()` 直接从 MySQL 加载导出，跳过网络请求

## 合规提醒

请在合理频率下使用，避免对豆瓣服务造成压力。若遇到访问频繁提示，应降低爬取频率或暂停采集。
