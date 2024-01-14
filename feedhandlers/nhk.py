import pytz, re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if 'news' in paths:
        api_url = 'https://www3.nhk.or.jp/nhkworld/data/en/news/{}.json'.format(paths[-1])
    else:
        logger.warning('unhandled url ' + url)
        return None

    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    item = {}
    item['id'] = api_json['data']['id']
    item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, api_json['data']['page_url'])
    item['title'] = api_json['data']['title']

    # Seems to be EST
    tz_est = pytz.timezone('US/Eastern')
    dt_est = datetime.fromtimestamp(int(api_json['data']['updated_at']) / 1000)
    dt = tz_est.localize(dt_est).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    # TODO: authors
    item['author'] = {"name": "NHK World"}

    if api_json['data'].get('categories'):
        item['tags'] = []
        item['tags'].append(api_json['data']['categories']['name'])

    item['content_html'] = ''
    poster = ''
    video_src = ''
    caption = ''
    if api_json['data'].get('videos'):
        video_xml = utils.get_url_html('{}://{}{}'.format(split_url.scheme, split_url.netloc, api_json['data']['videos']['config']))
        if video_xml:
            video_soup = BeautifulSoup(video_xml, 'lxml-xml')
            it = video_soup.find('file.stv')
            if it:
                # https://vod-stream.nhk.jp/nhkworld/upld/medias/en/news/20240103_07_149900_HQ/index.m3u8
                video_src = 'https://vod-stream.nhk.jp' + re.sub(r'_\w+$', '_HQ/index.m3u8', it.string)
                it = video_soup.find('image')
                if it:
                    poster = '{}://{}{}'.format(split_url.scheme, split_url.netloc, it.string)
                it = video_soup.find('media.title')
                if it:
                    caption = it.string

    if api_json['data'].get('thumbnails'):
        if api_json['data']['thumbnails'].get('large'):
            item['_image'] = api_json['data']['thumbnails']['large']
        elif api_json['data']['thumbnails'].get('middle'):
            item['_image'] = api_json['data']['thumbnails']['middle']
        elif api_json['data']['thumbnails'].get('small'):
            item['_image'] = api_json['data']['thumbnails']['small']
        elif poster:
            item['_image'] = poster
        if not caption and api_json['data']['thumbnails'].get('caption'):
            caption = api_json['data']['thumbnails']['caption']

    if video_src:
        item['content_html'] = utils.add_video(video_src, 'application/x-mpegURL', poster, caption)
    elif item.get('_image'):
        if item['_image'].startswith('/'):
            item['_image'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, item['_image'])
        item['content_html'] += utils.add_image(item['_image'], caption)

    item['summary'] = api_json['data']['description']

    item['content_html'] += '<p>' + re.sub(r'\n*<br />\n*<br />\n*', '</p><p>', api_json['data']['detail']) + '</p>'
    return item