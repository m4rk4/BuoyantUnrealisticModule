import json
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    return utils.clean_url(img_src) + '?w={}&q=75'.format(width)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    else:
        path = split_url.path
        if path.endswith('/'):
            path = path[:-1]
    next_url = '{}://{}/_next/data/{}/{}.json'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    #print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
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
    utils.write_file(next_data, './debug/debug.json')
    post_json = next_data['pageProps']['post']

    item = {}
    item['id'] = post_json['databaseId']
    item['url'] = 'https://www.thecollector.com/' + post_json['slug']
    item['title'] = post_json['title']

    # TODO: is date UTC?
    dt = datetime.fromisoformat(post_json['date']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['modified']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    item['author']['name'] = post_json['author']['node']['name']

    if post_json.get('tags') and post_json['tags'].get('edges'):
        item['tags'] = []
        for it in post_json['tags']['edges']:
            item['tags'].append(it['node']['name'])

    item['content_html'] = ''
    if post_json.get('subtitle'):
        item['content_html'] += '<p><em>{}</em></p>'.format(post_json['subtitle'])

    if post_json.get('featuredImage') and post_json['featuredImage'].get('node'):
        item['_image'] = post_json['featuredImage']['node']['sourceUrl']

    item['content_html'] += wp_posts.format_content(post_json['content'], item, site_json)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
