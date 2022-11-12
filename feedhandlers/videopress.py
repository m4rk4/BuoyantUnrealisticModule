import re, tldextract
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    # https://videopress.com/embed/D1vinM4b
    m = re.search(r'/embed/([^/]+)', url)
    if not m:
        logger.warning('unhandled videopress url ' + url)
        return None
    api_url = 'https://public-api.wordpress.com/rest/v1.1/videos/' + m.group(1)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/video.json')

    item = {}
    item['id'] = api_json['guid']
    item['url'] = url
    item['title'] = api_json['title']

    dt = datetime.fromisoformat(re.sub(r'\+(\d\d)(\d\d)$', r'+\1:\2', api_json['upload_date']))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['_image'] = api_json['poster']

    for it in ['dvd', 'hd', 'std']:
        if api_json['files'].get(it):
            item['_video'] = api_json['file_url_base']['https'] + api_json['files'][it]['mp4']
            break

    item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['_image'], item['title'])
    return item


def get_feed(args, save_debug=False):
    return None
