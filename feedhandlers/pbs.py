import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

from feedhandlers import rss
import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # For player.pbs.org embeds
    # https://player.pbs.org/widget/partnerplayer/3084901782/?chapterbar=false&endscreen=false&topbar=false&autoplay=false
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', string=re.compile(r'window\.videoBridge'))
    if not el:
        logger.warning('unable to find window.videoBridge data in ' + url)
        return None
    m = re.search(r'window\.videoBridge(.*)', el.string)
    i = m.group(1).find('{')
    j = m.group(1).rfind('}')
    video_json = json.loads(m.group(1)[i:j+1])
    if save_debug:
        utils.write_file(video_json, './debug/video.json')
    item = {}
    item['id'] = video_json['id']
    item['url'] = url
    item['title'] = video_json['title']

    dt = datetime.fromisoformat(video_json['air_date'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": video_json['program']['title']}

    item['_image'] = video_json['image_url']

    video_mp4 = ''
    video_m3u8 = ''
    for it in video_json['encodings']:
        src = utils.get_redirect_url(it)
        if src.endswith('.mp4'):
            video_mp4 = src
        elif src.endswith('.m3u8'):
            video_m3u8 = src

    caption = 'Watch: ' + item['title']

    if video_mp4:
        item['_video'] = video_mp4
        item['content_html'] = utils.add_video(video_mp4, 'video/mp4', item['_image'], caption)
    elif video_m3u8:
        item['_video'] = video_m3u8
        item['content_html'] = utils.add_video(video_m3u8, 'application/x-mpegURL', item['_image'], caption)

    if video_json.get('long_description'):
        item['summary'] = video_json['long_description']
    elif video_json.get('short_description'):
        item['summary'] = video_json['short_description']

    if 'embed' not in args and item.get('summary'):
        item['content_html'] += '<p>{}</p>'.format(item['summary'])
    return item
