import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    # https://embed.sendtonews.com/player4/embedcode.js?SC=i3p78nKk7p-2460057-6761&floatwidth=300&floatposition=bottom-right
    split_url = urlsplit(url)
    query = parse_qs(split_url.query)
    if not query.get('SC'):
        logger.warning('unhandled url ' + url)
        return None

    video_json = utils.get_url_json('https://embed.sendtonews.com/player4/data_read.php?cmd=loadInitial&SC={}&type=SINGLE'.format(query['SC'][0]))
    if not video_json:
        return None
    if save_debug:
        utils.write_file(video_json, './debug/video.json')

    video = video_json['playlistData'][0][0]

    item = {}
    item['id'] = query['SC'][0]
    item['url'] = url
    item['title'] = video['S_headLine']

    dt = datetime.strptime(video['S_sysDate'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": video['C_companyName']}

    if video.get('S_tags'):
        item['tags'] = video['S_tags'].split(', ')

    if video.get('thumbnailUrl'):
        item['_image'] = 'https:' + video['thumbnailUrl']

    if video.get('S_shortSummary'):
        item['summary'] = video['S_shortSummary']

    item['_video'] = 'https:' + video['configuration']['sources']['src']
    video_type = video['configuration']['sources']['type']
    poster = 'https:' + video['configuration']['poster']
    caption = 'Watch: ' + video['configuration']['title']
    item['content_html'] = utils.add_video(item['_video'], video_type, poster, caption)
    return item


def get_feed(args, save_debug=False):
    return None
