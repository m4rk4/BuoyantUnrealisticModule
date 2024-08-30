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
    if 'embeds' in paths:
        api_url = 'https://api.arte.tv/api/player/v2/config/{}/{}'.format(paths[-2], paths[-1])
    elif 'videos' in paths:
        i = paths.index('videos')
        api_url = 'https://api.arte.tv/api/player/v2/config/{}/{}'.format(paths[0], paths[i + 1])
    else:
        logger.warning('unhandled url ' + url)
        return None
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')
    attr_json = api_json['data']['attributes']

    item = {}
    item['id'] = api_json['data']['id']
    item['url'] = attr_json['metadata']['link']['url']
    item['title'] = attr_json['metadata']['subtitle'] + ' (' + attr_json['metadata']['title'] + ')'

    dt = datetime.fromisoformat(attr_json['rights']['begin'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {
        "name": attr_json['metadata']['title']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    if attr_json['metadata'].get('description'):
        item['summary'] = attr_json['metadata']['description']

    item['image'] = attr_json['metadata']['images'][0]['url']

    item['content_html'] = utils.add_video(attr_json['streams'][0]['url'], 'application/x-mpegURL', item['image'], item['title'])
    return item