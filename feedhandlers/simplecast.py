import re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if split_url.netloc == 'player.simplecast.com':
        paths = list(filter(None, split_url.path.split('/')))
        episode_json = utils.get_url_json('https://api.simplecast.com/episodes/{}'.format(paths[0]))
    else:
        # TODO: no longer works
        data = {"url": utils.clean_url(url)}
        episode_json = utils.post_url('https://api.simplecast.com/episodes/search', json_data=data)

    if not episode_json:
        return None
    if save_debug:
        utils.write_file(episode_json, './debug/audio.json')

    item = {}
    item['id'] = episode_json['id']
    item['url'] = episode_json['episode_url']
    item['title'] = episode_json['title']

    if episode_json.get('published_at'):
        dt = datetime.fromisoformat(episode_json['published_at']).astimezone(timezone.utc)
    elif episode_json.get('created_at'):
        dt = datetime.fromisoformat(episode_json['created_at']).astimezone(timezone.utc)
    else:
        logger.warning('unknown published date for ' + item['url'])
        dt = None
    if dt:
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, False)
    if episode_json.get('updated_at'):
        dt = datetime.fromisoformat(episode_json['updated_at']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['authors'] = []
    if episode_json.get('authors') and episode_json['authors'].get('collection'):
        item['authors'] = [{"name": x['name']} for x in episode_json['authors']['collection']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": episode_json['podcast']['title'] + ' with ' + re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
    else:
        item['author'] = {
            "name": episode_json['podcast']['title']
        }
    item['authors'].insert(0, {"name": episode_json['podcast']['title']})

    podcast_json = utils.get_url_json(episode_json['podcast']['href'])
    if podcast_json:
        item['author']['url'] = podcast_json['site']['url']

    if episode_json.get('image_url'):
        item['image'] = episode_json['image_url']
    elif episode_json['podcast'].get('image_url'):
        item['image'] = episode_json['podcast']['image_url']

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

    desc = ''
    if episode_json.get('description'):
        item['summary'] = episode_json['description']
        if 'embed' not in args:
            desc = '<p style="white-space:pre-line">' + episode_json['description'] + '</p>'

    duration = utils.calc_duration(episode_json['duration'])

    item['content_html'] = utils.add_audio_v2(item['_audio'], item.get('image'), item['title'], item['url'], item['author']['name'], item['author'].get('url'), item['_display_date'], duration, episode_json['audio_content_type'], desc=desc)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
