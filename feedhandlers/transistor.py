import json, pytz
from bs4 import BeautifulSoup
from datetime import datetime

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://share.transistor.fm/e/602f95a2/dark
    # https://share.transistor.fm/e/6a7ad271
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('div', id='embed-player')
    if not el:
        logger.warning('unable to find embed-player in ' + url)
        return None
    i = el['x-data'].find('{')
    j = el['x-data'].rfind('}') + 1
    audio_json = json.loads(el['x-data'][i:j])
    if save_debug:
        utils.write_file(audio_json, './debug/audio.json')
    ep_json = audio_json['episodes'][0]

    item = {}
    item['id'] = ep_json['id']
    item['url'] = ep_json['share_url']
    item['title'] = ep_json['title']

    tz_loc = pytz.timezone(config.local_tz)
    dt_loc = datetime.strptime(ep_json['formatted_published_at'], '%B %d, %Y')
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, date_only=True)

    item['author'] = {
        "name": audio_json['title'],
        "url": audio_json['website']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    item['image'] = ep_json['artwork']

    item['_audio'] = ep_json['trackable_media_url']
    attachment = {}
    attachment['url'] = item['_audio']
    attachment['mime_type'] = 'audio/mpeg'
    item['attachments'] = []
    item['attachments'].append(attachment)

    item['summary'] = ep_json['formatted_summary']

    item['content_html'] = utils.add_audio_v2(item['_audio'], item['image'], item['title'], item['url'], item['author']['name'], item['author']['url'], item['_display_date'], ep_json['duration'])
    if 'embed' not in args and ep_json.get('description'):
        item['content_html'] += '<p>' + ep_json['description'] + '</p>'
    return item


def get_feed(url, args, site_json, save_debug=False):
    return None