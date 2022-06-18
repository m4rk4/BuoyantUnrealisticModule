import math, re
from datetime import datetime
from urllib.parse import quote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)


def calculate_duration(sec):
    duration = []
    t = math.floor(float(sec) / 3600)
    if t >= 1:
        duration.append('{} hr'.format(t))
    t = math.ceil((float(sec) - 3600 * t) / 60)
    if t > 0:
        duration.append('{} min.'.format(t))
    return ', '.join(duration)


def get_content(url, args, save_debug=False):
    # Only handles single episodes
    # https://playlist.megaphone.fm/?e=ESP3970143369
    m = re.search(r'playlist\.megaphone\.fm/?\?([ep])=(\w+)', url)
    if not m:
        logger.warning('unhandled megaphone.fm url ' + url)
        return None

    if m.group(1) == 'p':
        api_url = 'https://player.megaphone.fm/playlist/' + m.group(2)
    else:
        api_url = 'https://player.megaphone.fm/playlist/episode/' + m.group(2)
    podcast_json = utils.get_url_json(api_url)
    if not podcast_json:
        return None
    if save_debug:
        utils.write_file(podcast_json, './debug/podcast.json')

    episode = podcast_json['episodes'][0]

    item = {}
    if m.group(1) == 'p':
        item['id'] = m.group(2)
        item['title'] = podcast_json['podcastTitle']
    else:
        item['id'] = episode['uid']
        item['title'] = episode['title']

    item['url'] = url

    dt = datetime.fromisoformat(episode['pubDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['author'] = {}
    item['author']['name'] = podcast_json['podcastTitle']

    item['_image'] = episode['imageUrl']
    item['_audio'] = episode['episodeUrlHRef']

    item['summary'] = episode['summary']

    if m.group(1) == 'p':
        poster = '{}/image?height=128&url={}'.format(config.server, quote_plus(item['_image']))
        desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4>'.format(item['url'], item['title'])
        item['content_html'] = '<table style="width:100%"><tr><td style="width:128px;"><img src="{}"/></td><td style="vertical-align:top;">{}</td></tr></table><table style="width:95%; margin-left:auto;">'.format(poster, desc)
        if 'embed' in args:
            n = 5
        else:
            n = -1
        poster = '{}/static/play_button-48x48.png'.format(config.server)
        for i, episode in enumerate(podcast_json['episodes']):
            duration = calculate_duration(episode['duration'])
            dt = datetime.fromisoformat(episode['pubDate'].replace('Z', '+00:00'))
            date = '{}. {}'.format(dt.strftime('%b'), dt.day)
            desc = '<small><strong><a href="{}">{}</a></strong><br/>{} · {}</small>'.format(episode['dataClipboardText'], episode['title'], date, duration)
            item['content_html'] += '<tr><td><a href="{}"><img src="{}"/></a></td><td>{}</td></tr>'.format(episode['audioUrl'], poster, desc)
        item['content_html'] += '</table>'
    else:
        item['_duration'] = calculate_duration(episode['duration'])
        poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))
        date = '{}. {}'.format(dt.strftime('%b'), dt.day)
        desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by {}<br/>{} · {}</small>'.format(item['url'], item['title'], item['author']['name'], date, item['_duration'])
        item['content_html'] = '<table style="width:100%"><tr><td style="width:128px;"><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;">{}</td></tr></table>'.format(item['_audio'], poster, desc)
        if not 'embed' in args:
            item['content_html'] += '<p>{}</p>'.format(item['summary'])
    return item


def get_feed(args, save_debug=False):
    return None
