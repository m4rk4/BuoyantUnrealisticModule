from datetime import datetime
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://video.wordpress.com/embed/LQVTPkex?hd=0&autoPlay=0&permalink=1&loop=0&preloadContent=metadata&muted=0&playsinline=0&controls=1&cover=1
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if paths[0] != 'embed':
        logger.warning('unhandled url ' + url)
        return None

    video_json = utils.get_url_json('https://public-api.wordpress.com/rest/v1.1/videos/{}'.format(paths[1]))
    if not video_json:
        return None
    if save_debug:
        utils.write_file(video_json, './debug/video.json')

    item = {}
    item['id'] = video_json['guid']
    item['url'] = url

    if video_json['files'].get('hd'):
        video_file = video_json['files']['hd']
    elif video_json['files'].get('dvd'):
        video_file = video_json['files']['dvd']
    elif video_json['files'].get('avc_240p'):
        video_file = video_json['files']['avc_240p']
    elif video_json['files'].get('std'):
        video_file = video_json['files']['std']

    if video_file.get('mp4'):
        item['title'] = video_file['mp4']
        item['_video'] = 'https://videos.files.wordpress.com/{}/{}'.format(video_json['guid'], video_file['mp4'])
        video_type = 'video/mp4'
    elif video_file.get('hls'):
        item['title'] = video_file['hls']
        item['_video'] = 'https://videos.files.wordpress.com/{}/{}'.format(video_json['guid'], video_file['hls'])
        video_type = 'application/x-mpegURL'

    if video_json.get('title'):
        item['title'] = video_json['title']

    dt = datetime.fromisoformat(video_json['upload_date'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if video_json.get('description'):
        item['summary'] = video_json['description']

    item['_image'] = video_json['poster']

    item['content_html'] = utils.add_video(item['_video'], video_type, item['_image'], item['title'])
    return item
