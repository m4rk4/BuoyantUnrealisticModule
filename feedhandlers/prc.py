import re
from bs4 import BeautifulSoup
from urllib.parse import urlsplit

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    args_copy = args.copy()
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    slug = paths[-1].split('.')[0]
    if paths[0] == 'fact-tank':
        post_url = '{}://{}/wp-json/wp/v2/{}?slug={}'.format(split_url.scheme, split_url.netloc, paths[0], slug)
    else:
        post_url = '{}://{}/{}/wp-json/wp/v2/posts?slug={}'.format(split_url.scheme, split_url.netloc, paths[0], slug)
    post_json = utils.get_url_json(post_url)
    if not post_json:
        logger.warning('failed to get post data from ' + post_url)
        return None
    return wp_posts.get_post_content(post_json[0], args_copy, save_debug)


def get_feed(args, save_debug=False):
    if '/wp-json/' in args['url']:
        return wp_posts.get_feed(args, save_debug)
    else:
        return rss.get_feed(args, save_debug, get_content)
