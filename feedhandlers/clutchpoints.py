import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    if urlsplit(img_src).netloc == 'wp.clutchpoints.com':
        return 'https://clutchpoints.com/_next/image?url={}&w={}&q=75'.format(quote_plus(img_src), width)
    return img_src


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

    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        m = re.search(r'"buildId":"([^"]+)"', page_html)
        if m and m.group(1) != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = m.group(1)
            utils.update_sites(url, site_json)
            next_url = '{}://{}/_next/data/{}/{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
            next_data = utils.get_url_json(next_url)
            if not next_data:
                return None
    return next_data


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/next.json')

    post_json = next_data['pageProps']['post']
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['id']

    split_url = urlsplit(url)
    item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, post_json['uri'])

    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['dateGmt']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['modifiedGmt']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {
        "name": post_json['author']['node']['name']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    if post_json.get('tags') and post_json['tags'].get('edges'):
        item['tags'] = []
        for it in post_json['tags']['edges']:
            item['tags'].append(it['node']['name'])

    if post_json.get('seo'):
        if post_json['seo'].get('opengraphDescription'):
            item['summary'] = post_json['seo']['opengraphDescription']
        elif post_json['seo'].get('metaDesc'):
            item['summary'] = post_json['seo']['metaDesc']
        elif post_json['seo'].get('twitterDescription'):
            item['summary'] = post_json['seo']['twitterDescription']

    item['content_html'] = ''
    if post_json.get('featuredImage') and post_json['featuredImage'].get('node'):
        item['image'] = post_json['featuredImage']['node']['sourceUrl']
        item['content_html'] += utils.add_image(resize_image(item['_image']))

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] += wp_posts.format_content(post_json['content'], item, site_json)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
