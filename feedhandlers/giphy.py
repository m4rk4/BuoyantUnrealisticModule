import json, re
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_image(img_src):
    split_url = urlsplit(img_src)
    return 'https://i.giphy.com{}'.format(split_url.path)


def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    m = re.search(r'^/(embed|gifs|media)/([^/]+)', split_url.path)
    if not m:
        logger.warning('unsupported giphy url ' + url)
        return None

    giphy_html = utils.get_url_html('https://giphy.com/gifs/' + m.group(2))
    if not giphy_html:
        return None
    if save_debug:
        utils.write_file(giphy_html, './debug/debug.html')

    m = re.search(r'Giphy\.renderDesktop\(document\.querySelector\(\'\.gif-detail-page\'\), {\s+gif: ({.*}),\n', giphy_html)
    if not m:
        return None
    giphy_json = json.loads(m.group(1))
    if save_debug:
        utils.write_file(giphy_json, './debug/giphy.json')

    item = {}
    item['id'] = giphy_json['id']
    item['url'] = giphy_json['url']
    item['title'] = giphy_json['title']

    # not sure about timezone
    if giphy_json.get('create_datetime'):
        date = giphy_json['create_datetime']
    elif giphy_json.get('import_datetime'):
        date = giphy_json['import_datetime']
    elif giphy_json.get('update_datetime'):
        date = giphy_json['update_datetime']
    elif giphy_json.get('trending_datetime'):
        date = giphy_json['trending_datetime']
    if date:
        date = re.sub('\+(\d\d)(\d\d)$', r'+\1:\2', date)
        dt = datetime.fromisoformat(date)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['author'] = {}
    if giphy_json.get('user'):
        item['author']['name'] = giphy_json['user']['display_name']
    elif giphy_json.get('username'):
        item['author']['name'] = giphy_json['username']

    if giphy_json.get('tags'):
        item['tags'] = giphy_json['tags'].copy()

    item['_image'] = get_image(giphy_json['images']['original_still']['url'])

    caption = '{} | <a href="{}">Watch on Giphy</a>'.format(giphy_json['title'], giphy_json['url'])
    if args:
        if 'mp4' in args:
            item['content_html'] = utils.add_video(get_image(giphy_json['images']['original']['mp4']), 'video/mp4',
                                                   item['_image'], caption)
        elif 'webp' in args:
            item['content_html'] = utils.add_video(get_image(giphy_json['images']['original']['webp']), 'video/mp4',
                                                   item['_image'], caption)
    if not item.get('content_html'):
        item['content_html'] = utils.add_image(get_image(giphy_json['images']['original']['url']), caption,
                                               giphy_json['images']['original']['width'])
    return item


def get_feed(args, save_debug=False):
    return None
