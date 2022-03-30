import json, re
from datetime import datetime, timezone

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    page_html = utils.get_url_html(url)
    m = re.search(r'videoObject = ({.*?});\s', page_html)
    if not m:
        logger.warning('unable to parse videoObject in ' + url)
        return None

    video_json = json.loads(m.group(1))
    if save_debug:
        utils.write_file(video_json, './debug/video.json')

    item = {}
    item['id'] = video_json['file_id']
    item['url'] = video_json['url']

    if video_json.get('title'):
        item['title'] = video_json['title']
    else:
        item['title'] = video_json['url']

    dt = datetime.fromtimestamp(video_json['date_added']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['_image'] = 'https:' + video_json['poster_url']
    if video_json['files'].get('mp4-mobile'):
        item['_video'] = 'https:' + video_json['files']['mp4-mobile']['url']
    else:
        item['_video'] = 'https:' + video_json['files']['mp4']['url']
    item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['_image'])
    return item

def get_feed(args, save_debug=False):
    return None
