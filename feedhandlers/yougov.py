import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    api_url = '{}://{}/api/article/{}'.format(split_url.scheme, split_url.netloc, '/'.join(paths[-4:]))
    meta_json = utils.get_url_json(api_url + '/meta/')
    if not meta_json:
        return None
    if save_debug:
        utils.write_file(meta_json, './debug/debug.json')

    item = {}
    item['id'] = meta_json['id']
    item['url'] = url
    item['title'] = meta_json['title']

    dt = datetime.fromisoformat(meta_json['start_publication'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    authors = []
    for it in meta_json['authors']:
        authors.append(it['fullname'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if meta_json.get('topics'):
        item['tags'] += meta_json['topics'].copy()
    if meta_json.get('entities'):
        for it in meta_json['entities']:
            if it['name'] not in item['tags']:
                item['tags'].append(it['name'])

    if meta_json.get('excerpt'):
        item['summary'] = meta_json['excerpt']

    item['content_html'] = ''
    if meta_json.get('main_image'):
        item['_image'] = 'https:' + meta_json['main_image'] + '?pw=1200'
        item['content_html'] += utils.add_image(item['_image'])

    content_html = utils.get_url_html(api_url + '/content/')
    if not content_html:
        return item
    if save_debug:
        utils.write_file(content_html, './debug/debug.html')

    soup = BeautifulSoup(content_html, 'html.parser')
    for el in soup.find_all('figure'):
        new_html = ''
        if el.iframe:
            new_html = utils.add_embed(el.iframe['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled figure in ' + item['url'])

    for el in soup.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('script'):
        el.decompose()

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    if '/feeds/' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    feed = None
    if '/topics/' in args['url']:
        split_url = urlsplit(args['url'])
        paths = list(filter(None, split_url.path.split('/')))
        api_url = '{}://{}/_pubapis/v5/us/search/content/articles/?category={}&limit=10'.format(split_url.scheme, split_url.netloc, paths[1])
        api_json = utils.get_url_json(api_url)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/feed.json')

        n = 0
        feed_items = []
        for article in api_json['data']:
            url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, article['url'])
            if save_debug:
                logger.debug('getting content for ' + url)
            item = get_content(url, args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break
        feed = utils.init_jsonfeed(args)
        feed['title'] = 'YouGov | ' + paths[1].title()
        feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)

    return feed