import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_json = utils.get_url_json(utils.clean_url(url) + '?format=json')
    if not page_json:
        return None
    if save_debug:
        utils.write_file(page_json, './debug/debug.json')

    site_url = page_json['site']['url']
    content_json = page_json['item']
    return get_item(content_json, site_url, args, site_json, save_debug)


def get_item(content_json, site_url, args, site_json, save_debug):
    item = {}
    item['id'] = content_json['id']
    item['url'] = site_url + content_json['link']
    item['title'] = content_json['title']

    dt = datetime.fromisoformat(content_json['created']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if content_json['modified'] != '0000-00-00 00:00:00':
        dt = datetime.fromisoformat(content_json['modified']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['author'] = {"name": content_json['author']['name']}

    item['tags'] = []
    if content_json.get('category'):
        item['tags'].append(content_json['category']['name'])
    if content_json.get('tags'):
        for it in content_json['tags']:
            item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''
    if content_json.get('image'):
        if content_json.get('imageLarge'):
            item['_image'] = site_url + content_json['imageLarge']
        else:
            item['_image'] = site_url + content_json['image']
        captions = []
        if content_json.get('image_caption'):
            captions.append(content_json['image_caption'])
        if content_json.get('image_credit'):
            captions.append(content_json['image_credit'])
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    if content_json.get('introtext'):
        item['summary'] = content_json['introtext']
        item['content_html'] += '<div style="font-weight:bold;">{}</div>'.format(content_json['introtext'])

    soup = BeautifulSoup(content_json['fulltext'], 'html.parser')
    for el in soup.find_all('table', class_='moduletable'):
        it = el.find('script', attrs={"src": re.compile(r'statcounter\.com|doubleclick\.net')})
        if not it:
            it = el.find(id=re.compile(r'div-gpt-ad'))
        if it:
            el.decompose()

    for el in soup.find_all(class_=['name-box-enabled', 'formula-bar-with-name-box-wrapper']):
        el.decompose()

    for el in soup.find_all('img'):
        if el['src'].startswith('http'):
            img_src = el['src']
        else:
            img_src = site_url + '/' + el['src']
        # TODO: captions?
        new_html = utils.add_image(img_src)
        new_el = BeautifulSoup(new_html, 'html.parser')
        for it in el.find_parents('p'):
            it.unwrap()
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        it = el.find_parent('p')
        if it:
            it.unwrap()
        el.insert_after(new_el)
        el.decompose()

    item['content_html'] += re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', str(soup))
    return item


def get_feed(url, args, site_json, save_debug=False):
    page_json = utils.get_url_json(utils.clean_url(url) + '?format=json')
    if not page_json:
        return None
    if save_debug:
        utils.write_file(page_json, './debug/feed.json')

    site_url = page_json['site']['url']

    n = 0
    feed_items = []
    for article in page_json['items']:
        article_url = site_url + article['link']
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_item(article, site_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    if page_json.get('category'):
        feed['title'] = '{} | {}'.format(page_json['category']['name'], page_json['site']['name'])
    else:
        feed['title'] = page_json['site']['name']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
