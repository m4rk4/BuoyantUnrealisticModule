import math, re
from datetime import datetime
from urllib.parse import quote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    m = re.search(r'embed\.acast\.com/([^/]+)/([^/]+)', url)
    if not m:
        m = re.search(r'play\.acast\.com/s/([^/]+)/([^/]+)', url)
        if not m:
            m = re.search(r'shows\.acast\.com/([^/]+)/episodes/([^/]+)', url)
            if not m:
                logger.warning('unhandled acast url ' + url)
                return None

    audio_json = utils.get_url_json('https://feeder.acast.com/api/v1/shows/{}/episodes/{}?showInfo=true'.format(m.group(1), m.group(2)))
    if not audio_json:
        return None
    if save_debug:
        utils.write_file(audio_json, './debug/audio.json')

    item = {}
    item['id'] = audio_json['id']
    item['url'] = audio_json['link']
    item['title'] = audio_json['title']

    dt = datetime.fromisoformat(audio_json['publishDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)

    item['author'] = {}
    item['author']['name'] = audio_json['show']['title']
    item['author']['url'] = audio_json['show']['link']
    item['authors'] = []
    item['authors'].append(item['author'])

    # if audio_json.get('keywords'):

    if audio_json.get('image'):
        item['image'] = audio_json['image']
    elif audio_json['images'].get('original'):
        item['image'] = audio_json['images']['original']
    elif audio_json['show'].get('image'):
        item['image'] = audio_json['show']['image']
    elif audio_json['show']['images'].get('original'):
        item['image'] = audio_json['show']['images']['original']

    item['_audio'] = audio_json['url']
    attachment = {
        "url": item['_audio'],
        "mime_type": "audio/mpeg"
    }
    item['attachments'] = []
    item['attachments'].append(attachment)

    item['summary'] = audio_json['subtitle']

    item['content_html'] = utils.add_audio(item['_audio'], item['image'], item['title'], item['url'], item['author']['name'], item['author']['url'], item['_display_date'], audio_json['duration'])

    if 'embed' not in args:
        item['content_html'] += '<p>' + item['summary'] + '</p>'
    return item
