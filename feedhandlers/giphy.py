import json, re
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_image(img_src):
    split_url = urlsplit(img_src)
    return 'https://i.giphy.com{}'.format(split_url.path)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if not (paths[0] == 'embed' or paths[0] == 'gifs' or paths[0] == 'media'):
        logger.warning('unsupported giphy url ' + url)
        return None

    giphy_html = ''
    for path in paths[1:]:
        giphy_html = utils.get_url_html('https://giphy.com/embed/' + path)
        if giphy_html:
            break
    if not giphy_html:
        return None
    if save_debug:
        utils.write_file(giphy_html, './debug/debug.html')

    m = re.search(r'gif:\s(\{.*?\}),\n', giphy_html)
    # m = re.search(r'Giphy\.renderDesktop\(document\.querySelector\(\'\.gif-detail-page\'\), {\s+gif: ({.*}),\n', giphy_html)
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
    else:
        date = ''
    if date:
        date = re.sub(r'\+(\d\d)(\d\d)$', r'+\1:\2', date)
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

    item['image'] = get_image(giphy_json['images']['original_still']['url'])
    if giphy_json['images']['original'].get('mp4'):
        item['_video'] = giphy_json['images']['original']['mp4']

    caption = '{} | <a href="{}">Watch on Giphy</a>'.format(giphy_json['title'], giphy_json['url'])
    if 'mp4' in args and giphy_json['images']['original'].get('mp4'):
        item['content_html'] = utils.add_video(get_image(giphy_json['images']['original']['mp4']), 'video/mp4', item['image'], caption, use_videojs=True)
    elif giphy_json['images']['original'].get('webp'):
        item['content_html'] = utils.add_image(get_image(giphy_json['images']['original']['webp']), caption, giphy_json['images']['original']['width'])
    else:
        # GIF
        item['content_html'] = utils.add_image(get_image(giphy_json['images']['original']['url']), caption, giphy_json['images']['original']['width'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return None
