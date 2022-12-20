import re
from datetime import datetime, timezone

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    # https://www.dailymotion.com/video/x8gg6m0
    m = re.search(r'/video/([^/]+)', url)
    if not m:
        logger.warning('unable to parse video id from ' + url)
        return None
    video_json = utils.get_url_json('https://www.dailymotion.com/player/metadata/video/' + m.group(1))
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

    item['_image'] = video_json['posters']['720']

    video = video_json['qualities']['auto'][0]
    item['content_html'] += utils.add_video(video['url'], video['type'], item['_image'], item['title'])
    return item
