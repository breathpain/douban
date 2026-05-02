# 豆瓣采集项目 - 成员A模块

本目录完成成员A任务：以豆瓣网站为主，提供基础 `requests` 爬虫、Selenium 动态页面兜底、图片下载，以及基础反爬策略实现。模块输出 JSON 和 CSV，方便成员B后续接 Scrapy/MySQL Pipeline，成员C后续做分析和可视化。

## 功能范围

- `requests` 基础采集：复用 Session、设置 Referer/Accept-Language、超时、重试。
- Selenium 动态处理：可选 Chrome 渲染，用于动态页面或普通请求遇到反爬后的兜底。
- 图片下载：下载豆瓣条目的封面图，按 URL 哈希命名，避免重复覆盖。
- 详情页采集：进入每部电影详情页，补充导演、编剧、主演、类型、国家、语言、上映日期、片长、IMDb 等字段。
- 反爬策略：随机 User-Agent、随机延迟、Cookie 注入、代理配置入口、异常状态识别。
- 数据落盘：同时生成 `douban_items.json` 和 `douban_items.csv`。

## 安装依赖

```powershell
pip install -r requirements.txt
```

如果要使用 Selenium，需要本机已经安装 Chrome，并且 Selenium 能找到匹配的 ChromeDriver。

如果当前环境提示找不到 `chromedriver`，先下载和 Chrome 主版本一致的 `chromedriver.exe`，然后运行时指定路径：

```powershell
python -m member_a_douban.cli --mode top250 --max-pages 1 --use-selenium --show-browser --driver-path "D:\tools\chromedriver.exe"
```

## 运行示例

采集豆瓣电影 Top250 第 1 页：

```powershell
python -m member_a_douban.cli --mode top250 --max-pages 1
```

只采集列表页，不进入详情页：

```powershell
python -m member_a_douban.cli --mode top250 --max-pages 1 --no-details
```

遇到动态内容或普通请求被拦截时，启用 Selenium：

```powershell
python -m member_a_douban.cli --mode top250 --max-pages 1 --use-selenium
```

采集自定义豆瓣页面：

```powershell
python -m member_a_douban.cli --mode urls --url "https://movie.douban.com/top250"
```

带 Cookie 运行：

```powershell
python -m member_a_douban.cli --cookie "bid=xxxx; dbcl2=xxxx"
```

## 输出文件

默认输出到：

- `data/member_a/douban_items.json`
- `data/member_a/douban_items.csv`
- `data/member_a/images/`

字段包括：

- `title`
- `url`
- `rating`
- `comment_count`
- `summary`
- `image_url`
- `source_page`
- `image_file`
- `director`
- `screenwriter`
- `actors`
- `genres`
- `country`
- `language`
- `release_date`
- `runtime`
- `imdb`
- `detail_error`

## 分工说明

成员A当前代码主要位于 `member_a_douban/`，可在报告中统计为独立模块。成员B可以读取 CSV/JSON 后写入 MySQL，或复用 `parser.py` 的字段结构改造成 Scrapy Item。成员C可以直接使用输出文件做数据分析、情感分析和图表生成。

## 合规提醒

运行时请降低频率，优先采集公开列表页，不要绕过登录、验证码或权限控制。若豆瓣返回验证码或访问频繁提示，应停止采集或改用更低频率。
