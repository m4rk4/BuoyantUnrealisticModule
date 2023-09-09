import math, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://www.spreaker.com/episode/56476059
    # https://api.spreaker.com/v2/episodes/56476059/play.mp3
    episode_id = ''
    m = re.search(r'\/episodes?/(\d+)', url)
    if m:
        episode_id = m.group(1)
    else:
        page_html = utils.get_url_html(url)
        if page_html:
            soup = BeautifulSoup(page_html, 'lxml')
            el = soup.find(attrs={"data-station_url": True})
            if el:
                m = re.search(r'\/episodes?/(\d+)', el['data-station_url'])
                if m:
                    episode_id = m.group(1)
    if not episode_id:
        logger.warning('unhandled spreaker.com url ' + url)
        return None

    api_url = 'https://api.spreaker.com/v2/episodes/{}?export=episode_segments'.format(episode_id)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/audio.json')
    episode_json = api_json['response']['episode']

    item = {}
    item['id'] = episode_json['episode_id']
    item['url'] = episode_json['site_url']
    item['title'] = episode_json['title']

    item['_image'] = episode_json['image_url']
    poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))

    item['_audio'] = episode_json['playback_url']
    item['content_html'] = '<table><tr><td style="width:128px;"><a href="{}"><img src="{}"/></a></td>'.format(item['_audio'], poster)

    item['content_html'] += '<td style="vertical-align:top;"><div style="font-size:1.2em; font-weight:bold;"><a href="{}">{}</a></div><div style="font-size:0.9em;">'.format(item['url'], item['title'])

    if episode_json.get('show'):
        item['content_html'] += '<a href="{}">{}</a> '.format(episode_json['show']['site_url'], episode_json['show']['title'])

    if episode_json.get('author'):
        item['author'] = {}
        item['author']['name'] = episode_json['author']['fullname']
        item['content_html'] += 'by <a href="{}">{}</a></div>'.format(episode_json['author']['site_url'], episode_json['author']['fullname'])

    dt = datetime.fromisoformat(episode_json['published_at']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)

    s = float(episode_json['duration'] / 1000)
    h = math.floor(s / 3600)
    s = s - h * 3600
    m = math.floor(s / 60)
    s = s - m * 60
    if h > 0:
        duration = '{:0.0f}:{:02.0f}:{:02.0f}'.format(h, m, s)
    else:
        duration = '{:0.0f}:{:02.0f}'.format(m, s)

    item['content_html'] += '</div><div style="font-size:0.9em;">{}&nbsp;&bull;&nbsp;{}</div></td></tr></table>'.format(item['_display_date'], duration)

    if episode_json.get('description_html'):
        item['summary'] = episode_json['description_html']
        if not 'embed' in args:
            item['content_html'] += utils.add_blockquote(item['summary'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
