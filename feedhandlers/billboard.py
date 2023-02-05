import re
from bs4 import BeautifulSoup
from urllib.parse import urlsplit

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    post = ''
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    slug = paths[-1]
    if '/pro/' in split_url.path:
        post_url = 'https://www.billboard.com/wp-json/wp/v2/billboard_pro_post?slug={}'.format(slug)
        post_json = utils.get_url_json(post_url)
        if not post_json:
            return None
        post = post_json[0]
    elif '/video/' in split_url.path:
        post_url = 'https://www.billboard.com/wp-json/wp/v2/pmc_top_video?slug={}'.format(slug)
        post_json = utils.get_url_json(post_url)
        if not post_json:
            return None
        post = post_json[0]
        args_copy = args.copy()
        args_copy['nolead'] = ''
        item = wp_posts.get_post_content(post, args_copy, save_debug)
        if not item:
            return None
        page_html = utils.get_url_html(url)
        if page_html:
            soup = BeautifulSoup(page_html, 'html.parser')
            el = soup.find(attrs={"data-video-showcase-trigger": True})
            if el:
                item['content_html'] = utils.add_embed('https://cdn.jwplayer.com/players/{}-.js'.format(el['data-video-showcase-trigger'])) + item['content_html']
                return item
        item['content_html'] = utils.add_image(item['_image']) + item['content_html']
        return item
    else:
        m = re.search(r'\d+$', slug)
        if m:
            post_url = 'https://www.billboard.com/wp-json/wp/v2/posts/{}'.format(m.group(0))
            post_json = utils.get_url_json(post_url)
            if not post_json:
                return None
            post = post_json
        else:
            logger.warning('unhandled url ' + url)
            return None

    return wp_posts.get_post_content(post, args, site_json, save_debug)


def get_feed(url, args, site_json, save_debug=False):
    if '/wp-json/' in args['url']:
        return wp_posts.get_feed(url, args, site_json, save_debug)
    else:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

def test_handler():
    feeds = ['https://www.billboard.com/feed',
             'https://www.billboard.com/pro/feed/',
             'https://www.billboard.com/vcategory/billboard-videos/feed/']
    for url in feeds:
        get_feed({"url": url}, True)
