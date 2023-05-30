import json, re
from bs4 import BeautifulSoup
from dateutil import parser
from urllib.parse import urlsplit

import utils
from feedhandlers import wp_posts

import logging

logger = logging.getLogger(__name__)

def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if 'video' not in paths:
        return wp_posts.get_content(url, args, site_json, save_debug)

    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', string=re.compile(r'gncaVideoPlayerSettings'))
    if not el:
        logger.warning('unable to determine gncaVideoPlayerSettings in ' + url)
        return None
    player_str = el.string.strip()
    n =  player_str.find('{')
    player_json = json.loads(player_str[n:-1])
    if save_debug:
        utils.write_file(player_json, './debug/video.json')

    video_json = player_json['jw']['playlist'][0]
    item = {}
    item['id'] = video_json['videoPostId']
    item['url'] = video_json['descriptionUrl']
    item['title'] = video_json['title']

    dt = parser.parse(video_json['metadata']['airDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['tags'] = video_json['keywords'].split(',')
    item['_image'] = video_json['image']
    item['summary'] = video_json['description']

    caption = '<a href="{}">{}</a>'.format(item['url'], item['title'])
    src = next((it for it in video_json['sources'] if it['type'] == 'mp4'), None)
    if src:
        item['content_html'] = utils.add_video(src['file'], 'video/mp4', item['_image'], caption)
    else:
        item['content_html'] = utils.add_video(video_json['sources'][0], 'application/x-mpegURL', item['_image'], caption)

    if 'embed' in args or 'embed' in paths:
        item['content_html'] += '<p>{}</p>'.format(item['summary'])
    return item
