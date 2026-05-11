"""Scrapy Item definitions for Douban crawler.

Each field maps 1:1 to the original DoubanItem dataclass in member_a_douban.parser,
allowing seamless conversion between the two representations.
"""

import scrapy


class DoubanItem(scrapy.Item):
    """Scrapy Item for a Douban movie entry with full detail info."""

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
