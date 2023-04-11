from urllib.parse import urlsplit

from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    ftb_site_json = site_json.copy()
    ftb_site_json['wpjson_path'] = 'https://freethoughtblogs.com/{}/wp-json'.format(paths[0])
    return wp_posts.get_content(url, args, ftb_site_json, save_debug)


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
