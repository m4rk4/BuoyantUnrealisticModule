import feedparser, json, re
from bs4 import BeautifulSoup
from urllib.parse import parse_qs, quote_plus, urlsplit, unquote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if not split_url.fragment:
        logger.warning('unsupported url ' + url)
        return None

    page_html = utils.get_url_html(url)
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')

    if split_url.fragment.startswith('a'):
        content_id = split_url.fragment[1:]
    else:
        logger.warning('unhandled link fragment {} in {}'.format(split_url.fragment, url))
    content = soup.find('div', id=content_id)
    if content:
        el = content.find(class_=['L1', 'sharebox'])
        if el and el.a:
            return utils.get_content(el.a['href'], args, save_debug)
    logger.warning('unhandled content in ' + url)
    return None


def get_feed(url, args, site_json, save_debug=False):
    news_feed = utils.get_url_html(url)
    if not news_feed:
        return None
    try:
        d = feedparser.parse(news_feed)
    except:
        logger.warning('Feedparser error ' + url)
        return None

    n = 0
    feed_items = []
    for entry in d.entries:
        if entry.get('description'):
            m = re.search(r'href=\"([^\"]+)\"', entry.description)
            if m:
                if save_debug:
                    logger.debug('getting content for ' + m.group(1))
                item = utils.get_content(m.group(1), args, save_debug)
                if item:
                    if utils.filter_item(item, args) == True:
                        feed_items.append(item)
                        n += 1
                        if 'max' in args:
                            if n == int(args['max']):
                                break
    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
