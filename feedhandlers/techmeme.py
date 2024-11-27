import feedparser, json, re
from bs4 import BeautifulSoup
from datetime import datetime
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
    if not content:
        logger.warning('unhandled content in ' + url)
        return None

    item = {}
    item['id'] = content_id
    item['url'] = url

    el = soup.find('meta', attrs={"property": "og:title"})
    if el:
        item['title'] = el['content']

    item['author'] = {"name": "Techmeme"}
    item['authors'] = []
    item['authors'].append(item['author'])

    # Use date from Mastodon link - seems to be created shortly after the article is posted
    el = content.find(attrs={"mdurl": True})
    if el:
        split_url = urlsplit(el['mdurl'])
        paths = list(filter(None, split_url.path.split('/')))
        api_url = 'https://{}/api/v1/statuses/{}'.format(split_url.netloc, paths[-1])
        api_json = utils.get_url_json(api_url)
        if api_json:
            dt = datetime.fromisoformat(api_json['created_at'])
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)

    el = soup.find('META', attrs={"PROPERTY": "og:image"})
    if el:
        item['image'] = el['CONTENT']

    content_link = ''
    el = content.find('a', class_='ourh')
    if el and el.get('href'):
        content_link = el['href']
    else:
        el = content.find(class_='sharebox', attrs={"pml": content_id})
        if el:
            content_link = el['url']

    item['content_html'] = ''
    if content_link:
        content_item = utils.get_content(content_link, {"embed": True}, save_debug=False)
        if content_item:
            item['content_html'] += content_item['content_html']
        if 'date_published' not in item:
            item['date_published'] = content_item['date_published']
            item['_timestamp'] = content_item['_timestamp']
            item['_display_date'] = content_item['_display_date']
    else:
        logger.warning('unable to find main article link in ' + url)

    el = content.select('div:has(> div:is(.dbpt, .mlk))')
    if el:
        for it in el[-1].find_all(class_=['dxd', 'show', 'exm', 'shr']):
            it.decompose()
        for it in el[-1].find_all(class_=['drhed', 'moreat']):
            it['style'] = 'font-size:1.1em; font-weight:bold;'
        for it in el[-1].find_all(class_=['di', 'lnkr']):
            it['style'] = 'margin:8px 0 8px 12px;'
        for it in el[-1].find_all('span', attrs={"style": re.compile(r'background:')}):
            it.unwrap()
        item['content_html'] += el[-1].decode_contents()

    return item


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
