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
    lede = ''
    if '/watch/video/' in url:
        page_html = utils.get_url_html(url)
        if page_html:
            soup = BeautifulSoup(page_html, 'html.parser')
            el = soup.find(class_='hero-section')
            if el:
                it = el.find('iframe')
                if it:
                    lede = utils.add_embed(it['src'])
        args_copy['nolead'] = ''
        post_url = '{}://{}/wp-json/wp/v2/nerdist_video?slug={}'.format(split_url.scheme, split_url.netloc, slug)
    else:
        post_url = '{}://{}/wp-json/wp/v2/{}?slug={}'.format(split_url.scheme, split_url.netloc, paths[0], slug)
    post = utils.get_url_json(post_url)
    if not post:
        logger.warning('failed to get post data from ' + post_url)
        return None
    item = wp_posts.get_post_content(post[0], args_copy, save_debug)
    if item and lede:
        item['content_html'] = lede + item['content_html']
    return item


def get_feed(args, save_debug=False):
    if '/wp-json/' in args['url']:
        return wp_posts.get_feed(args, save_debug)
    else:
        return rss.get_feed(args, save_debug, get_content)
