"""豆瓣爬虫 Scrapy Item 定义。

每个字段与 requests_douban.parser 中原有的 DoubanItem 数据类一一对应，
允许两个表示之间无缝转换。
"""

import scrapy


class DoubanItem(scrapy.Item):
    """豆瓣电影条目的 Scrapy Item，包含完整详情信息。"""

    title = scrapy.Field()
    url = scrapy.Field()
    rank = scrapy.Field()
    title_cn = scrapy.Field()
    title_en = scrapy.Field()
    rating = scrapy.Field()
    comment_count = scrapy.Field()
    summary = scrapy.Field()
    image_url = scrapy.Field()
    source_page = scrapy.Field()
    image_file = scrapy.Field()
    director = scrapy.Field()
    screenwriter = scrapy.Field()
    actors = scrapy.Field()
    genres = scrapy.Field()
    country = scrapy.Field()
    language = scrapy.Field()
    release_date = scrapy.Field()
    runtime = scrapy.Field()
    imdb = scrapy.Field()
    short_comments = scrapy.Field()
    detail_error = scrapy.Field()
