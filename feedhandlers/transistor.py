import html, json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://share.transistor.fm/e/602f95a2/dark
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find(attrs={"x-data": "transistor.audioEmbedPlayer"})
    if not el:
        logger.warning('unable to find transistor.audioEmbedPlayer in ' + url)
        return None
    data_json = json.loads(html.unescape(el['data-episodes']))
    if save_debug:
        utils.write_file(data_json, './debug/audio.json')
    audio_json = data_json[0]

    item = {}
    item['id'] = audio_json['id']
    item['url'] = audio_json['share_url']
    item['title'] = audio_json['title']

    dt = datetime.strptime(audio_json['formatted_published_at'], '%B %d, %Y')
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)

    item['author'] = {"name": audio_json['author']}

    item['_image'] = audio_json['artwork']
    poster = '{}/image?url={}&height=128&overlay=audio'.format(config.server, quote_plus(item['_image']))

    item['_audio'] = audio_json['trackable_media_url']
    attachment = {}
    attachment['url'] = item['_audio']
    attachment['mime_type'] = 'audio/mpeg'
    item['attachments'] = []
    item['attachments'].append(attachment)

    item['summary'] = audio_json['formatted_summary']

    item['content_html'] = '<table><tr><td style="width:128px;"><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;"><a href="{}"><b>{}</b></a><br/><small>{}</small><br/><small>{}&nbsp;&bull;&nbsp;{}</small></td></tr></table>'.format(item['_audio'], poster, item['url'], item['title'], item['author']['name'], item['_display_date'], audio_json['duration_in_mmss'])
    if 'embed' not in args:
        item['content_html'] += '<p>{}</p>'.format(item['summary'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return None