import math, re
from datetime import datetime
from urllib.parse import quote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    # Only handles single episodes
    # https://playlist.megaphone.fm/?e=ESP3970143369
    m = re.search(r'playlist\.megaphone\.fm/\?e=(\w+)', url)
    if not m:
        m = re.search(r'player\.megaphone\.fm/(\w+)', url)
        if not m:
            logger.warning('unable to parse episode id from ' + url)
            return None

    podcast_json = utils.get_url_json('https://player.megaphone.fm/playlist/episode/{}'.format(m.group(1)))
    if not podcast_json:
        return None
    if save_debug:
        utils.write_file(podcast_json, './debug/podcast.json')

    episode = podcast_json['episodes'][0]

    item = {}
    item['id'] = episode['uid']
    item['url'] = 'https://playlist.megaphone.fm/?e={}'.format(episode['uid'])
    item['title'] = episode['title']

    dt = datetime.fromisoformat(episode['pubDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['author'] = {}
    item['author']['name'] = podcast_json['podcastTitle']

    item['_image'] = episode['imageUrl']
    item['_audio'] = episode['episodeUrlHRef']

    item['summary'] = episode['summary']

    duration = []
    t = math.floor(float(episode['duration']) / 3600)
    if t >= 1:
        duration.append('{} hr'.format(t))
    t = math.ceil((float(episode['duration']) - 3600 * t) / 60)
    if t > 0:
        duration.append('{} min.'.format(t))
    item['_duration'] = ', '.join(duration)

    poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))
    desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by {}<br/>{}</small>'.format(item['url'], item['title'], item['author']['name'], item['_duration'])
    item['content_html'] = '<div><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><div style="overflow:hidden;">{}</div><div style="clear:left;"></div></div>'.format(item['_audio'], poster, desc)
    if not 'embed' in args:
        item['content_html'] += '<div>{}</div>'.format(item['summary'])
    return item


def get_feed(args, save_debug=False):
    return None
