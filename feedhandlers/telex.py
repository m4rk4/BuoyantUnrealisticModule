import pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    api_url = 'https://{}/api/articles/{}'.format(split_url.netloc, paths[-1])
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    item = {}
    item['id'] = api_json['id']
    item['url'] = url
    item['title'] = api_json['title']

    tz_loc = pytz.timezone('US/Eastern')
    dt_loc = datetime.fromtimestamp(api_json['pubDate'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if api_json.get('updatedAt'):
        dt_loc = datetime.fromtimestamp(api_json['updatedAt'])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_modified'] = dt.isoformat()

    authors = []
    for it in api_json['articleAuthors']:
        authors.append(it['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if api_json.get('tags'):
        item['tags'] = []
        for it in api_json['tags']:
            item['tags'].append(it['name'])

    if api_json.get('ogDescription'):
        item['summary'] = api_json['ogDescription']

    item['content_html'] = ''
    if api_json.get('coverImage'):
        item['_image'] = api_json['coverImage']
        item['content_html'] += utils.add_image(item['_image'])

    soup = BeautifulSoup(api_json['content'], 'html.parser')
    for el in soup.find_all('advanced-image'):
        new_html = utils.add_image(el['pic1'], el.get('image-alt'))
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all('oembed'):
        new_html = utils.add_embed(el['url'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        if el.parent and el.parent.name == 'figure':
            el.parent.replace_with(new_el)
        else:
            el.replace_with(new_el)

    for el in soup.find_all('blockquote', class_=False):
        new_html = utils.add_blockquote(el.decode_contents(), False)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all('placeholder-view'):
        if el.parent and el.parent.name == 'p':
            el.parent.decompose()
        else:
            el.decompose()

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
