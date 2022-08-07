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
    if video_json.get('file_id'):
        item['id'] = video_json['file_id']
    elif video_json.get('extract_id'):
        item['id'] = video_json['extract_id']
    else:
        item['id'] = video_json['shortcode']

    if video_json.get('url'):
        item['url'] = video_json['url']
    elif video_json.get('extract_id'):
        item['url'] = 'https://streamable.com/m/' + video_json['extract_id']

    if video_json.get('title'):
        item['title'] = video_json['title']
    elif video_json.get('extract_id'):
        item['title'] = video_json['extract_id'].replace('-', ' ').title()

    if video_json.get('date_added'):
        dt = datetime.fromtimestamp(video_json['date_added']).replace(tzinfo=timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    if video_json.get('poster_url'):
        item['_image'] = video_json['poster_url']
    elif video_json.get('thumbnail_url'):
        item['_image'] = video_json['thumbnail_url']
    else:
        item['_image'] = ''
    if item['_image'].startswith('//'):
        item['_image'] = 'https:' + item['_image']

    if video_json['files'].get('mp4-mobile'):
        item['_video'] = video_json['files']['mp4-mobile']['url']
    else:
        item['_video'] = video_json['files']['mp4']['url']
    if item['_video'].startswith('//'):
        item['_video'] = 'https:' + item['_video']

    item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['_image'])
    return item

def get_feed(args, save_debug=False):
    return None
