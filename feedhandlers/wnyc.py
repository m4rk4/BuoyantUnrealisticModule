import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import npr, rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if split_url.path.startswith('/widgets/'):
        m = re.search(r'/audio/json/(\d+)/', url)
        if not m:
            logger.warning('unable to determine id in ' + url)
            return None
        api_json = utils.get_url_json('https://api.wnyc.org/api/v1/story/{}/'.format(m.group(1)))
        if not api_json:
            return None
        split_url = urlsplit(api_json['results'][0]['url'])

    api_json = utils.get_url_json('https://api.wnyc.org/api/v3/' + split_url.path)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    if api_json['data']['attributes']['item-type'] == 'nprarticle':
        return npr.get_content(api_json['data']['attributes']['canonical-url'], {}, {}, save_debug)

    item = {}
    item['id'] = api_json['data']['id']
    item['url'] = api_json['data']['attributes']['url']
    item['title'] = api_json['data']['attributes']['title']

    dt = datetime.fromisoformat(api_json['data']['attributes']['newsdate']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)

    item['author'] = {
        "name": api_json['data']['attributes']['headers']['brand']['title'],
        "url": api_json['data']['attributes']['headers']['brand']['url']
    }

    item['tags'] = api_json['data']['attributes']['tags'].copy()

    item['summary'] = api_json['data']['attributes']['tease']

    item['content_html'] = ''

    if 'embed' not in args:
        if api_json['data']['attributes'].get('image-main'):
            item['_image'] = api_json['data']['attributes']['image-main']['url']
            captions = []
            if api_json['data']['attributes']['image-main'].get('caption'):
                captions.append(api_json['data']['attributes']['image-main']['caption'])
            if api_json['data']['attributes']['image-main'].get('credits-name'):
                captions.append(api_json['data']['attributes']['image-main']['credits-name'])
            if api_json['data']['attributes']['image-main'].get('source'):
                captions.append(api_json['data']['attributes']['image-main']['source']['name'])
            item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

        if api_json['data']['attributes'].get('body'):
            item['content_html'] += api_json['data']['attributes']['body']

    if api_json['data']['attributes'].get('audio'):
        item['_audio'] = utils.get_redirect_url(api_json['data']['attributes']['audio'])
        attachment = {}
        attachment['url'] = item['_audio']
        attachment['mime_type'] = 'audio/mpeg'
        item['attachments'] = []
        item['attachments'].append(attachment)

        poster = '{}/image?url={}&height=128&overlay=audio'.format(config.server, quote_plus(api_json['data']['attributes']['headers']['brand']['logo-image']['url']))
        item['content_html'] += '<table><tr><td style="width:128px;"><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;"><a href="{}"><b>{}</b></a><br/><a href="{}"><small>{}</small></a><br/><small>{}&nbsp;&bull;&nbsp;{}</small></td></tr></table>'.format(item['_audio'], poster, item['url'], item['title'], item['author']['url'], item['author']['name'], item['_display_date'], api_json['data']['attributes']['audio-duration-readable'])

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
