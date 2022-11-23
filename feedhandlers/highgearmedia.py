import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    m = re.search(r'^(\d+)', paths[-1])
    if not m:
        logger.warning('unhandled url ' + url)
        return None
    api_url = '{}://{}/api/load-article/{}'.format(split_url.scheme, split_url.netloc, m.group(1))
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    item = {}
    item['id'] = m.group(1)
    item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, api_json['url'])
    item['title'] = api_json['title']

    soup = BeautifulSoup(api_json['body'], 'html.parser')

    el = soup.find('time')
    if el:
        date = re.sub(r'\+(\d\d)(\d\d)$', r'+\1:\2', el['datetime'])
        dt = datetime.fromisoformat(date)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": api_json['author']}

    if api_json['targets'].get('tags'):
        item['tags'] = api_json['targets']['tags'].split(',')

    gallery_images = []
    if soup.find(class_='gallery'):
        gallery_json = utils.get_url_json('{}://{}/api/load-gallery/{}'.format(split_url.scheme, split_url.netloc, item['id']))
        if gallery_json:
            gallery_images = gallery_json['images'].copy()

    item['content_html'] = ''
    el = soup.find(class_='hero-wrap-parallax')
    if el:
        caption = ''
        for i, image in enumerate(gallery_images):
            if image['url_l'] == el['data-image-src-l']:
                caption = image['title']
                del gallery_images[i]
                break
        item['_image'] = el['data-image-src-l']
        item['content_html'] += utils.add_image(el['data-image-src-l'], caption)

    body = soup.find('section', class_='article-body')
    for el in body.find_all(class_='hgmLayout'):
        el.unwrap()

    for el in body.find_all(class_='image_wrapper'):
        for i, image in enumerate(gallery_images):
            if image['url_l'] == el.img['data-src-l']:
                del gallery_images[i]
                break
        new_html = utils.add_image(el.img['data-src-l'], el.img['title'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in body.find_all('blockquote', class_='twitter-tweet'):
        links = el.find_all('a')
        new_html = utils.add_embed(links[-1]['href'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in body.find_all('div'):
        if el.find(id='widgetLoaded'):
            el.decompose()

    item['content_html'] += str(body.decode_contents())

    if gallery_images:
        item['content_html'] += '<h2>Gallery ({} photos)</h2>'.format(len(gallery_images))
        for image in gallery_images:
            item['content_html'] += utils.add_image(image['url_l'], image['title'])

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])

    #item['content_html'] += str(soup)
    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
