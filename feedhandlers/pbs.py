import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # For player.pbs.org embeds
    # https://player.pbs.org/widget/partnerplayer/3084901782/?chapterbar=false&endscreen=false&topbar=false&autoplay=false
    # https://player.pbs.org/viralplayer/3108506079/
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
    item['url'] = 'https://player.pbs.org/viralplayer/' + video_json['id'] + '/'
    item['title'] = video_json['title']

    dt = datetime.fromisoformat(video_json['air_date']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {
        "name": video_json['program']['title']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    item['image'] = video_json['image_url']

    video_mp4 = ''
    video_m3u8 = ''
    for it in video_json['encodings']:
        src = utils.get_redirect_url(it)
        if src.endswith('.mp4'):
            video_mp4 = src
        elif src.endswith('.m3u8'):
            video_m3u8 = src

    if video_m3u8:
        item['_video'] = video_m3u8
        item['_video_type'] = 'application/x-mpegURL'
    elif video_mp4:
        item['_video'] = video_mp4
        item['_video_type'] = 'video/mp4'

    caption = 'Watch: ' + item['title']

    item['content_html'] = utils.add_video(item['_video'], item['_video_type'], item['image'], caption, use_videojs=True)

    if video_json.get('long_description'):
        item['summary'] = video_json['long_description']
    elif video_json.get('short_description'):
        item['summary'] = video_json['short_description']

    if 'embed' not in args and item.get('summary'):
        item['content_html'] += '<p>' + item['summary'] + '</p>'
    return item
