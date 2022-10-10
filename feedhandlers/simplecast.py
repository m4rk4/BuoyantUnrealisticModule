import math, re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    if split_url.netloc == 'player.simplecast.com':
        paths = list(filter(None, split_url.path.split('/')))
        episode_json = utils.get_url_json('https://api.simplecast.com/episodes/{}/player'.format(paths[0]))
        if episode_json:
            episode_url = episode_json['episode_url']
    else:
        episode_url = utils.clean_url(url)

    data = {"url": episode_url}
    episode_json = utils.post_url('https://api.simplecast.com/episodes/search', json_data=data)
    if not episode_json:
        return None
    if save_debug:
        utils.write_file(episode_json, './debug/audio.json')

    item = {}
    item['id'] = episode_json['id']
    item['url'] = episode_json['episode_url']
    item['title'] = episode_json['title']

    dt = datetime.fromisoformat(episode_json['published_at']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)
    dt = datetime.fromisoformat(episode_json['updated_at']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    if episode_json.get('authors') and episode_json['authors'].get('collection'):
        for it in episode_json['authors']['collection']:
            authors.append(it['name'])
    item['author'] = {}
    if authors:
        item['author']['name'] = '{} with {}'.format(episode_json['podcast']['title'], re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)))
    else:
        item['author']['name'] = episode_json['podcast']['title']

    if episode_json.get('image_url'):
        item['_image'] = episode_json['image_url']
    elif episode_json['podcast'].get('image_url'):
        item['_image'] = episode_json['podcast']['image_url']
    if item.get('_image'):
        poster = '{}/image?url={}&height=128&overlay=audio'.format(config.server, quote_plus(item['_image']))
    else:
        poster = '{}/image?height=128&width=128&overlay=audio'.format(config.server)

    attachment = {}
    audio_json = utils.get_url_json(episode_json['audio_file']['href'])
    if audio_json:
        attachment['url'] = audio_json['enclosure_url']
        attachment['mime_type'] = audio_json['content_type']
    else:
        attachment['url'] = episode_json['audio_file_url']
        attachment['mime_type'] = episode_json['audio_content_type']
    item['attachments'] = []
    item['attachments'].append(attachment)
    item['_audio'] = attachment['url']

    item['summary'] = episode_json['description']

    duration = []
    t = math.floor(float(episode_json['duration']) / 3600)
    if t >= 1:
        duration.append('{} hr'.format(t))
    t = math.ceil((float(episode_json['duration']) - 3600 * t) / 60)
    if t > 0:
        duration.append('{} min.'.format(t))

    item['content_html'] = '<table><tr><td style="width:128px;"><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;"><a href="{}"><b>{}</b></a><br/><small>{}</small><br/><small>{}&nbsp;&bull;&nbsp;{}</small></td></tr></table>'.format(item['_audio'], poster, item['url'], item['title'], item['author']['name'], item['_display_date'], ', '.join(duration))
    if 'embed' not in args:
        item['content_html'] += '<p>{}</p>'.format(item['summary'])
    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
