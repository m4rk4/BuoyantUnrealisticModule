import math, re
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

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


def get_content(url, args, site_json, save_debug=False):
    # Only handles single episodes
    # https://playlist.megaphone.fm/?e=ESP3970143369
    item = {}
    api_url = ''
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if split_url.netloc == 'megaphone.link':
        item['id'] = paths[0]
        api_url = 'https://player.megaphone.fm/playlist/episode/' + item['id']
    elif split_url.netloc == 'playlist.megaphone.fm':
        query = parse_qs(split_url.query)
        if query.get('p'):
            item['id'] = query['p'][0]
            api_url = 'https://player.megaphone.fm/playlist/' + item['id']
        elif query.get('e'):
            item['id'] = query['e'][0]
            api_url = 'https://player.megaphone.fm/playlist/episode/' + item['id']
    elif split_url.netloc == 'player.megaphone.fm' and len(paths) == 1:
        item['id'] = paths[0]
        api_url = 'https://player.megaphone.fm/playlist/episode/' + item['id']

    if not api_url:
        logger.warning('unhandled url ' + url)
        return None

    podcast_json = utils.get_url_json(api_url)
    if not podcast_json:
        return None
    if save_debug:
        utils.write_file(podcast_json, './debug/podcast.json')

    episode = podcast_json['episodes'][0]

    if '/episode/' in api_url:
        item['id'] = episode['uid']
        item['title'] = episode['title']
    else:
        item['title'] = podcast_json['podcastTitle']

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

    if '/episode/' in api_url:
        item['_duration'] = calculate_duration(episode['duration'])
        poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))
        date = '{}. {}'.format(dt.strftime('%b'), dt.day)
        desc = '<span style="font-size:1.2em; font-weight:bold;"><a href="{}">{}</a></span><br/>by {}<br/>{} · {}'.format(item['url'], item['title'], item['author']['name'], date, item['_duration'])
        item['content_html'] = '<table style="width:100%"><tr><td style="width:128px;"><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;">{}</td></tr></table>'.format(item['_audio'], poster, desc)
        if not 'embed' in args:
            item['content_html'] += '<p>{}</p>'.format(item['summary'])
    else:
        poster = '{}/image?height=128&url={}'.format(config.server, quote_plus(item['_image']))
        desc = '<span style="font-size:1.2em; font-weight:bold;"><a href="{}">{}</a></span>'.format(item['url'], item['title'])
        item['content_html'] = '<table style="width:100%"><tr><td style="width:128px;"><img src="{}"/></td><td style="vertical-align:top;">{}</td></tr></table><table style="margin-left:32px; border-left:3px solid #ccc"><tr><td colspan="2"><span style="font-size:1.1em; font-weight:bold;">Episodes:</span></td></tr>'.format(poster, desc)
        poster = '{}/static/play_button-48x48.png'.format(config.server)
        for i, episode in enumerate(podcast_json['episodes']):
            duration = calculate_duration(episode['duration'])
            dt = datetime.fromisoformat(episode['pubDate'].replace('Z', '+00:00'))
            date = '{}. {}'.format(dt.strftime('%b'), dt.day)
            desc = '<b><a href="{}">{}</a></b><br/><small>{} · {}</small>'.format(episode['dataClipboardText'], episode['title'], date, duration)
            item['content_html'] += '<tr><td><a href="{}"><img src="{}"/></a></td><td>{}</td></tr>'.format(episode['audioUrl'], poster, desc)
            if 'embed' in args and i >= 4:
                break
        item['content_html'] += '</table>'
    return item


def get_feed(url, args, site_json, save_debug=False):
    return None
