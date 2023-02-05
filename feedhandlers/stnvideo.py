import pytz, re
from datetime import datetime
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)

def get_content(url, args, site_json, save_debug=False):
    # url looks like https://embed.sendtonews.com/player2/embedcode.php?SC=M6lyh1M9hJ-1931712-8423&autoplay=on
    m = re.search(r'SC=([^&]+)', url)
    if not m:
        logger.warning('unhandled url ' + url)

    api_url = 'https://embed.sendtonews.com/player4/data_read.php?cmd=loadInitial&SC={}&type=SINGLE'.format(m.group(1))
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    if save_debug:
        utils.write_file(api_json, './debug/video.json')

    video_json = api_json['playlistData'][0][0]

    item = {}
    item['id'] = m.group(1)
    item['url'] = url
    item['title'] = video_json['S_headLine']
    tz_est = pytz.timezone('US/Eastern')
    dt_est = datetime.fromisoformat(video_json['S_sysDate'])
    dt = tz_est.localize(dt_est).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    item['author'] = {"name": video_json['C_companyName']}
    item['tags'] = video_json['S_tags'].split(',')
    item['_image'] = 'https:' + video_json['thumbnailUrl']
    split_url = urlsplit(item['_image'])
    item['_video'] = 'https://{}/{}'.format(split_url.netloc, video_json['videoConversions']['MP4300k'])
    item['summary'] = video_json['S_shortSummary']
    item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['_image'], item['title'])
    if not 'embed' in args:
        item['content_html'] += '<p>{}</p>'.format(item['summary'])
    return item

def get_feed(url, args, site_json, save_debug):
    return None