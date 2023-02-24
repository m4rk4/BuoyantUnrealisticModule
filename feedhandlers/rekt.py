import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from markdown2 import markdown
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    path += '.json'

    next_url = '{}://{}/_next/data/{}/en{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        m = re.search(r'"buildId":"([^"]+)"', page_html)
        if m and m.group(1) != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = m.group(1)
            utils.update_sites(url, site_json)
            next_url = '{}://{}/_next/data/{}/en{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
            next_data = utils.get_url_json(next_url)
            if not next_data:
                return None
    return next_data


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    item = {}
    item['id'] = next_data['pageProps']['slug']
    item['url'] = url
    item['title'] = next_data['pageProps']['data']['title']

    item['author'] = {"name": "REKT"}

    # Date format: month/day/year
    d = next_data['pageProps']['data']['date'].split('/')
    if len(d[2]) == 2:
        d[2] = '20' + d[2]
    dt = datetime(int(d[2]), int(d[0]), int(d[1])).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)

    item['tags'] = next_data['pageProps']['data']['tags'].copy()

    content_html = markdown(next_data['pageProps']['content'])
    soup = BeautifulSoup(content_html, 'html.parser')
    for el in soup.find_all('img'):
        if not item.get('_image'):
            item['_image'] = el['src']
        new_html = utils.add_image(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        if el.parent and el.parent.name == 'p':
            el.parent.insert_after(new_el)
            el.parent.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all('blockquote'):
        el['style'] = 'border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px;'

    item['content_html'] = str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    n = 0
    items = []
    feed = utils.init_jsonfeed(args)
    soup = BeautifulSoup(page_html, 'lxml')
    for el in soup.find_all(class_='post-title'):
        url = 'https://rekt.news' + el.a['href']
        if save_debug:
            logger.debug('getting content from ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed['items'] = items.copy()
    return feed
