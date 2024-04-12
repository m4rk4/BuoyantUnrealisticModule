import json, pytz
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlencode, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_data(url):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', id='data', attrs={"type": "application/json"})
    if not el:
        logger.warning('unable to find json data in ' + url)
        return None
    return json.loads(el.string)


def get_content(url, args, site_json, save_debug=False):
    data_json = get_data(url)
    if not data_json:
        return None
    if save_debug:
        utils.write_file(data_json, './debug/debug.json')
    article_json = data_json['article'][0]

    item = {}
    item['id'] = article_json['id']
    item['url'] = url
    item['title'] = article_json['title']

    tz = pytz.timezone(config.local_tz)
    dt = dateutil.parser.parse(article_json['created']).replace(tzinfo=tz)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['modified']).replace(tzinfo=tz)
    item['date_modified'] = dt.isoformat()

    item['author'] = {"name": "Pearl Jam"}

    if article_json.get('square_image_file'):
        item['_image'] = article_json['square_image_file']
    elif article_json.get('hero_image_file'):
        item['_image'] = article_json['hero_image_file']

    item['content_html'] = ''
    soup = BeautifulSoup(article_json['article'], 'html.parser')
    if not soup.find('img') and item.get('_image'):
        item['content_html'] += utils.add_image(item['_image'])

    for el in soup.find_all('img'):
        new_el = BeautifulSoup(utils.add_image(el['src']), 'html.parser')
        it = el.find_parent('p')
        if it:
            it.replace_with(new_el)
        else:
            el.replace_with(new_el)


    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    data_json = get_data(url)
    if not data_json:
        return None
    if save_debug:
        utils.write_file(data_json, './debug/feed.json')

    n = 0
    feed_items = []
    for article in data_json['articles']:
        article_url = 'https://pearljam.com/{}/{}'.format(article['category'].lower(), article['slug'])
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_content(article_url, args, site_json, save_debug)
        if item:
          if utils.filter_item(item, args) == True:
            feed_items.append(item)
            n += 1
            if 'max' in args:
                if n == int(args['max']):
                    break
    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
