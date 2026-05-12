"""豆瓣爬虫数据质检脚本。

读取爬取的 JSON 数据文件，统计各项字段的完整性。
"""
import json

# 加载爬取的豆瓣电影数据
d = json.load(open('F:/douban/scrapy_douban/data/crawler/douban_items.json', 'r', encoding='utf-8'))

# 统计各类数据完整性
print('total:', len(d))
print('with director:', sum(1 for i in d if i.get('director')))
print('with comments:', sum(1 for i in d if i.get('short_comments')))

# 输出爬取失败的条目
err_items = [i for i in d if i.get('detail_error')]
print('with detail_error:', len(err_items))
for i in err_items[:5]:
    print(f'  "{i["title"]}" error="{i.get("detail_error","")[:80]}"')
