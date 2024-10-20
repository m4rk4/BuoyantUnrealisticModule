import re
from datetime import datetime, timezone

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://cdn.jwplayer.com/players/QjZKj8Po-AjIcq1uW.js
    # https://content.jwplatform.com/players/K1j14B6g.html
    # https://cdn.jwplayer.com/manifests/uqYcHzXZ.m3u8
    # https://cdn.jwplayer.com/videos/q6Eqk0Xt-4VHSaSK0.mp4
    m = re.search(r'/(players|previews|v2/media|manifests|videos)/([^-\.]+)', url)
    if not m:
        return None

    video_json = utils.get_url_json('https://cdn.jwplayer.com/v2/media/' + m.group(2))
    if not video_json:
        video_json = utils.get_url_json('https://cdn.jwplayer.com/v2/playlists/' + m.group(2))
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
    item['image'] = image['src']
    item['_image'] = image['src']

    video = next((it for it in video_json['playlist'][0]['sources'] if it['type'] == 'application/vnd.apple.mpegurl'), None)
    if video:
        item['_video'] = video['file']
        item['_video_type'] = video['type']

    videos = []
    for video in video_json['playlist'][0]['sources']:
        if video.get('type') == 'video/mp4':
            videos.append(video)
    if videos:
        video = utils.closest_dict(videos, 'height', 720)
        if '_video' not in item:
            item['_video'] = video['file']
            item['_video_type'] = video['type']
        else:
            item['_video_mp4'] = video['file']

    if '_video' not in item:
        video = video_json['playlist'][0]['sources'][0]
        item['_video'] = video['file']
        item['_video_type'] = video['type']

    if video_json['playlist'][0].get('description'):
        item['summary'] = video_json['playlist'][0]['description']

    item['content_html'] = utils.add_video(item['_video'], item['_video_type'], item['image'], 'Watch: ' + item['title'])

    if 'embed' not in args and 'summary' in item:
        item['content_html'] += '<p>' + item['summary'] + '</p>'
    return item


def get_feed(url, args, site_json, save_debug=False):
    return None
