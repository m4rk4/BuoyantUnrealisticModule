import re
from datetime import datetime, timezone

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://cdn.jwplayer.com/players/QjZKj8Po-AjIcq1uW.js
    m = re.search(r'/(players|previews|v2/media)/([^-]+)', url)
    if not m:
        return None

    video_json = utils.get_url_json('https://cdn.jwplayer.com/v2/media/' + m.group(2))
    if not video_json:
        return None
    if save_debug:
        utils.write_file(video_json, './debug/video.json')

    item = {}
    item['id'] = video_json['playlist'][0]['mediaid']
    item['url'] = video_json['playlist'][0]['link']
    item['title'] = video_json['playlist'][0]['title']

    dt = datetime.fromtimestamp(video_json['playlist'][0]['pubdate']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    image = utils.closest_dict(video_json['playlist'][0]['images'], 'width', 1080)
    item['_image'] = image['src']

    videos = []
    for video in video_json['playlist'][0]['sources']:
        if video.get('type') == 'video/mp4':
            videos.append(video)
    video = utils.closest_dict(videos, 'height', 480)
    item['_video'] = video['file']

    if video_json['playlist'][0].get('description'):
        item['summary'] = video_json['playlist'][0]['description']

    caption = 'Watch: ' + item['title']
    item['content_html'] = utils.add_video(video['file'], video['type'], image['src'], caption)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return None
