import re
from bs4 import BeautifulSoup, Comment
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    slug = paths[-1].split('.')[0]
    wpjson_path = '/wp-json'
    posts_path = '/wp/v2/posts'

    post_url = '{}://{}{}{}?slug={}'.format(split_url.scheme, split_url.netloc, wpjson_path, posts_path, slug)
    post_json = utils.get_url_json(post_url)
    if not post_json:
        return None
    post = post_json[0]
    if save_debug:
        utils.write_file(post, './debug/debug.json')

    item = {}
    item['id'] = post['id']
    item['url'] = post['link']
    item['title'] = BeautifulSoup('<p>{}</p>'.format(post['title']['rendered']), 'lxml').get_text()

    dt = datetime.fromisoformat(post['date_gmt']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post['modified_gmt']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['tags'] = []
    if post.get('categories'):
        for it in post['categories']:
            tag_url = '{}://{}{}/wp/v2/categories/{}'.format(split_url.scheme, split_url.netloc, wpjson_path, it)
            tag_json = utils.get_url_json(tag_url)
            if tag_json:
                item['tags'].append(tag_json['name'])
    if post.get('tags'):
        for it in post['tags']:
            tag_url = '{}://{}{}/wp/v2/tags/{}'.format(split_url.scheme, split_url.netloc, wpjson_path, it)
            tag_json = utils.get_url_json(tag_url)
            if tag_json:
                item['tags'].append(tag_json['name'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''

    page_html = utils.get_url_html(url)
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find(class_='post-image')
    if el:
        img = el.find('img')
        if img:
            if img.get('srcset'):
                img_src = utils.image_from_srcset(img['srcset'], 1000)
            else:
                img_src = img['src']
        item['_image'] = img_src
        item['content_html'] += utils.add_image(img_src)

    item['author'] = {}
    soup = BeautifulSoup(post['content']['rendered'], 'lxml')
    el = soup.find('p')
    m = re.search(r'^by (.*)', el.get_text().strip())
    if m:
        item['author']['name'] = m.group(1)
        el.decompose()
    else:
        item['author']['name'] = 'ScripType Publishing'

    for el in soup.find_all(class_='themify_builder_content'):
        el.decompose()

    for el in soup.find_all(text=lambda text: isinstance(text, Comment)):
        el.extract()

    item['content_html'] += wp_posts.format_content(str(soup), item)
    return item

def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)