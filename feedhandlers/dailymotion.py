import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://www.dailymotion.com/video/x8gg6m0
    # https://geo.dailymotion.com/player/xrcz4.html?video=x8pnavd&playlist=x7wdsm&mute=true
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    video_id = ''
    if 'video' in paths:
        m = re.search(r'/video/([^/]+)', split_url.path)
        if m:
            video_id = m.group(1)
    else:
        params = parse_qs(split_url.query)
        if 'video' in params:
            video_id = params['video'][0]
    if not video_id:
        logger.warning('unable to parse video id from ' + url)
        return None

    video_json = utils.get_url_json('https://www.dailymotion.com/player/metadata/video/' + video_id)
    if not video_json:
        return None
    if save_debug:
        utils.write_file(video_json, './debug/video.json')

    item = {}
    item['id'] = video_json['id']
    item['url'] = video_json['url']
    item['title'] = video_json['title']

    dt = datetime.fromtimestamp(video_json['created_time']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if video_json.get('owner'):
        item['author'] = {"name": video_json['owner']['screenname']}

    if video_json.get('tags'):
        item['tags'] = video_json['tags'].copy()

    item['_image'] = video_json['posters']['720']

    video = video_json['qualities']['auto'][0]

    item['content_html'] = utils.add_video(video['url'], video['type'], item['_image'], item['title'], use_proxy=True)
    return item
