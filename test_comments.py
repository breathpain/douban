"""Test parse_movie_comments on real Douban comments pages."""
import sys
sys.path.insert(0, '.')

from requests_douban.http_client import DoubanHttpClient
from requests_douban.config import CrawlConfig
from requests_douban.parser import parse_movie_comments, has_next_page
from requests_douban.selenium_renderer import SeleniumRenderer
from urllib.parse import urlencode

cfg = CrawlConfig(
    request_timeout=15, retry_times=3,
    delay_min=1.2, delay_max=3.5,
    cookie=None,
    chrome_driver_path=r'F:\douban\chromedriver.exe',
    use_selenium=True, selenium_headless=True,
)

# --- Test 1: HTTP client ---
client = DoubanHttpClient(cfg)
url = 'https://movie.douban.com/subject/1292052/comments?' + urlencode({'status': 'P'})

print('=' * 60)
print('TEST 1: HTTP client')
print('URL:', url)
try:
    result = client.get(url, referer='https://movie.douban.com/subject/1292052/')
    print('Status:', result.status_code)
    print('Final URL:', result.url)
    if '<title>' in result.text:
        title = result.text.split('<title>')[1].split('</title>')[0]
        print('Title:', title)
    comments = parse_movie_comments(result.text, 999)
    print('Comments found:', len(comments))
    print('Has next page:', has_next_page(result.text))
    if comments:
        print('First comment:', comments[0][:80] if len(comments[0]) > 80 else comments[0])
except Exception as e:
    print('ERROR:', e)

# --- Test 2: Selenium ---
print()
print('=' * 60)
print('TEST 2: Selenium render_comments')
try:
    with SeleniumRenderer(cfg) as renderer:
        result2 = renderer.render_comments(url, 10)
        print('Status:', result2.status_code)
        print('Final URL:', result2.url)
        if '<title>' in result2.text:
            title2 = result2.text.split('<title>')[1].split('</title>')[0]
            print('Title:', title2)
        comments2 = parse_movie_comments(result2.text, 999)
        print('Comments found:', len(comments2))
        print('Has next page:', has_next_page(result2.text))
        if comments2:
            print('First comment:', comments2[0][:80] if len(comments2[0]) > 80 else comments2[0])
except Exception as e:
    import traceback
    traceback.print_exc()

# --- Test 3: Selenium render (no render_comments) ---
print()
print('=' * 60)
print('TEST 3: Selenium render (plain)')
try:
    with SeleniumRenderer(cfg) as renderer:
        result3 = renderer.render(url)
        print('Status:', result3.status_code)
        print('Final URL:', result3.url)
        comments3 = parse_movie_comments(result3.text, 999)
        print('Comments found:', len(comments3))
        print('Has next page:', has_next_page(result3.text))
except Exception as e:
    import traceback
    traceback.print_exc()

print()
print('=' * 60)
print('DONE')
