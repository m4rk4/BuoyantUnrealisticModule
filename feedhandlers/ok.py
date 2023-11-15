import html, json
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://ok.ru/video/1574576261742
    # https://ok.ru/videoembed/1574576261742
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if not (len(paths) == 2 and 'video' in paths[0]):
        logger.warning('unhandled url ' + url)
        return None

    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find(attrs={"data-module": "OKVideo"})
    if not el:
        logger.warning('unable to find OKVideo in ' + url)
        return None

    data_options = json.loads(html.unescape(el['data-options']))
    meta_data = json.loads(data_options['flashvars']['metadata'])
    if save_debug:
        utils.write_file(meta_data, './debug/video.json')

    item = {}
    if meta_data.get('movie'):
        item['id'] = meta_data['movie']['id']
        item['url'] = meta_data['movie']['url']
        item['title'] = meta_data['movie']['title']
        item['_image'] = meta_data['movie']['poster']
        video = next((it for it in meta_data['videos'] if it['name'] == 'sd'), None)
        if not video:
            video = next((it for it in meta_data['videos'] if it['name'] == 'mobile'), None)
            if not video:
                video = meta_data['videos'][0]
        item['content_html'] = utils.add_video(video['url'], 'video/mp4', item['_image'], item['title'], use_videojs=True)
    else:
        logger.warning('unhandled video metadata in ' + url)
    return item
