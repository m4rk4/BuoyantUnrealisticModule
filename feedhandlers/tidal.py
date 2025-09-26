import curl_cffi
from datetime import datetime, timezone
from urllib.parse import urlsplit

import config, utils
from feedhandlers import wp_posts_v2

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    base_url = split_url.scheme + '://' + split_url.netloc
    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[0] != 'magazine':
        logger.warning('unhandled url ' + url)
        return None

    api_url = 'https://tidal.com/magazine/api' + split_url.path
    article_json = utils.get_url_json(api_url, site_json=site_json)
    if not article_json:
        return None    
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = 'https://tidal.com/magazine' + article_json['href']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['datetime']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if article_json.get('author'):
        api_url = 'https://tidal.com/magazine/api/magazine/author/' + str(article_json['author'])
        author_json = utils.get_url_json(api_url, site_json=site_json)
        if author_json:
            item['author'] = {
                "name": article_json['name']
            }
            item['authors'] = []
            item['authors'].append(item['author'])

    if article_json.get('tags'):
        item['tags'] = [x['name'] for x in article_json['tags']]

    if article_json.get('preamble'):
        item['summary'] = article_json['preamble']

    if article_json.get('image'):
        item['image'] = article_json['image']

    item['content_html'] = ''
    for block in article_json['blocks']:
        item['content_html'] += wp_posts_v2.format_block(block, site_json, base_url)

    return item
