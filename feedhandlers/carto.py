import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    m = re.search(r'JSON\.parse\(\'(.*)\'\), opt', page_html)
    if m:
        cartodb = re.sub(r'\\([\w"])', r'\1', m.group(1))
        cartodb = re.sub(r'\\([\w"])', r'\1', cartodb)
        cartodb_json = json.loads(cartodb)
        if save_debug:
            utils.write_file(cartodb_json, './debug/debug.json')
    else:
        cartodb_json = None

    soup = BeautifulSoup(page_html, 'lxml')
    meta = {}
    for el in soup.find_all('meta'):
        if el.get('property'):
            key = el['property']
        elif el.get('name'):
            key = el['name']
        else:
            continue
        if meta.get(key):
            if isinstance(meta[key], str):
                if meta[key] != el['content']:
                    val = meta[key]
                    meta[key] = []
                    meta[key].append(val)
            if el['content'] not in meta[key]:
                meta[key].append(el['content'])
        else:
            meta[key] = el['content']
    if save_debug:
        utils.write_file(meta, './debug/meta.json')

    item = {}
    if cartodb_json:
        item['id'] = cartodb_json['id']
        item['title'] = cartodb_json['title']
        dt = datetime.fromisoformat(cartodb_json['updated_at'].replace('Z', '+00:00'))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
    else:
        item['id'] = meta['og:url']
        item['title'] = meta['og:title']
    item['url'] = meta['og:url']
    item['author'] = {"name": meta['author']}
    item['tags'] = meta['keywords'].split(', ')
    item['_image'] = meta['og:image']
    item['summary'] = meta['description']
    caption = '<a href="{}">{}</a>'.format(item['url'], item['title'])
    item['content_html'] = utils.add_image(item['_image'], caption, link=item['url'])
    if not 'embed' in args:
        item['content_html'] += '<p>{}</p>'.format(item['summary'])
    return item
