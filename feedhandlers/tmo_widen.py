import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://tmo.widen.net/view/video/kkfwjxjoro/4981195_hometown-grant-video-1212-announce_DELV_v05.mp4?t.download=true&amp;u=100np3
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', id='bootstrap-data')
    if not el:
        logger.warning('unable to find bootstrap-data in ' + url)
        return None

    i = el.string.find('{')
    j = el.string.rfind('}') + 1
    data_json = json.loads(el.string[i:j])
    if save_debug:
        utils.write_file(data_json, './debug/debug.json')

    item = {}
    item['id'] = data_json['assetExternalId']
    item['url'] = url
    item['title'] = data_json['previews']['filename']
    item['content_html'] = utils.add_video(data_json['previews']['hls'], 'application/x-mpegURL', data_json['previews']['poster'], ' | '.join(data_json['previews']['captions']))
    return item
