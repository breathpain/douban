import json
d = json.load(open('F:/douban/scrapy_douban/data/crawler/douban_items.json', 'r', encoding='utf-8'))
print('total:', len(d))
print('with director:', sum(1 for i in d if i.get('director')))
print('with comments:', sum(1 for i in d if i.get('short_comments')))
err_items = [i for i in d if i.get('detail_error')]
print('with detail_error:', len(err_items))
for i in err_items[:5]:
    print(f'  "{i["title"]}" error="{i.get("detail_error","")[:80]}"')
