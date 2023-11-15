import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

from feedhandlers import rss
import utils

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
        query = ''
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
        query = '?slug=' + paths[-1]
    next_url = '{}://{}/_next/data/{}{}.json{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, query)
    #print(next_url)
    next_data = utils.get_url_json(next_url)
    if not next_data:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if el:
            next_data = json.loads(el.string)
            if next_data['buildId'] != site_json['buildId']:
                logger.debug('updating {} buildId'.format(split_url.netloc))
                site_json['buildId'] = next_data['buildId']
                utils.update_sites(url, site_json)
            return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')
    post_json = next_data['pageProps']['post']

    item = {}
    item['id'] = post_json['slug']
    item['url'] = url
    item['title'] = post_json['meta']['title']

    authors = []
    for it in post_json['meta']['authors']:
        authors.append(it['fullName'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if post_json['meta'].get('category'):
        item['tags'] = post_json['meta']['category'].copy()

    if post_json['meta'].get('description'):
        item['summary'] = post_json['description']

    if post_json['meta'].get('featuredImage'):
        item['_image'] = post_json['meta']['featuredImage']

    item['content_html'] = ''
    # TODO: decode content. Seems to be React JSX
    # https://labs.quansight.org/blog/numba-polynomial-support
    return item