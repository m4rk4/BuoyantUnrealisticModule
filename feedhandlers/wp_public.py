import html, re
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    slug = paths[-1].split('.')[0]

    api_url = 'https://public-api.wordpress.com/rest/v1.1/sites/{}/posts/slug:{}'.format(site_json['site_id'], slug)
    post_json = utils.get_url_json(api_url)
    if not post_json:
        return None
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['ID']
    item['url'] = post_json['URL']
    item['title'] = post_json['title']
    if re.search(r'&[#\w]+;', item['title']):
        item['title'] = html.unescape(item['title'])

    dt = datetime.fromisoformat(post_json['date'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['modified'])
    item['date_modified'] = dt.isoformat()

    if post_json['author'].get('first_name') and post_json['author'].get('last_name'):
        item['author'] = {"name": '{} {}'.format(post_json['author']['first_name'], post_json['author']['last_name'])}
    elif post_json['author'].get('name'):
        item['author'] = {"name": post_json['author']['name']}

    item['tags'] = []
    if post_json.get('categories'):
        for key, val in post_json['categories'].items():
            item['tags'].append(val['name'])
    if post_json.get('tags'):
        for key, val in post_json['tags'].items():
            item['tags'].append(val['name'])
    if not item.get('tags'):
        del item['tags']

    if post_json.get('featured_image'):
        item['_image'] = post_json['featured_image']
    elif post_json.get('post_thumbnail'):
        item['_image'] = post_json['post_thumbnail']['URL']
    elif post_json.get('attachments'):
        for key, val in post_json['attachments'].items():
            if val.get('mime_type') and 'image' in val['mime_type']:
                item['_image'] = val['URL']
                break

    if post_json.get('excerpt'):
        item['summary'] = post_json['excerpt']

    item['content_html'] = ''
    if 'add_lede_img' in args and item.get('_image'):
        item['content_html'] += utils.add_image(item['_image'])

    item['content_html'] += wp_posts.format_content(post_json['content'], item)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
