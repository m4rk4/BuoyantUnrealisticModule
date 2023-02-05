import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    if split_url.path.startswith('/'):
        path = split_url.path
    else:
        path = '/' + split_url.path
    return 'https://d2kspx2x29brck.cloudfront.net/{}x0/filters:format(webp){}'.format(width, path)


def get_next_json(url, build_id=''):
    if not build_id:
        sites_json = utils.read_json_file('./sites.json')
        build_id = sites_json['interestingengineering']['buildId']
    else:
        sites_json = None
    next_url = 'https://interestingengineering.com/_next/data/' + build_id
    split_url = urlsplit(url)
    if split_url.path:
        next_url += split_url.path + '.json'
    else:
        next_url += '/index.json'

    next_json = utils.get_url_json(next_url, retries=1)
    if not next_json:
        logger.debug('updating interestingengineering.com buildId')
        article_html = utils.get_url_html(url)
        m = re.search(r'"buildId":"([^"]+)"', article_html)
        if m:
            build_id = m.group(1)
            if not sites_json:
                sites_json = utils.read_json_file('./sites.json')
            sites_json['interestingengineering']['buildId'] = build_id
            utils.write_file(sites_json, './sites.json')
            next_json = utils.get_url_json('https://interestingengineering.com/_next/data/{}{}.json'.format(build_id, split_url.path))
            if not next_json:
                return None

    if next_json['pageProps'].get('__N_REDIRECT'):
        url = 'https://interestingengineering.com' + next_json['pageProps']['__N_REDIRECT']
        next_json = get_next_json(url, build_id)
    return next_json


def get_content(url, args, site_json, save_debug=False):
    next_json = get_next_json(url)
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/debug.json')

    content_json = next_json['pageProps']['articleData']['content']
    item = {}
    item['id'] = content_json['id']
    item['url'] = 'https://interestingengineering.com/' + content_json['url']
    item['title'] = content_json['title']

    dt = datetime.strptime(content_json['publish_date'], '%d %b %Y, %H:%M:%S').replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if content_json.get('update_date'):
        dt = datetime.strptime(content_json['update_date'], '%d %b %Y, %H:%M:%S').replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

    authors = []
    for key, val in content_json['author'].items():
        for it in val:
            authors.append('{} {}'.format(it['name'], it['surname']))
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if content_json.get('keywords'):
        item['tags'] = content_json['keywords'].split(', ')
    else:
        item['tags'] = []
    if content_json.get('tags'):
        for it in content_json['tags']:
            if it not in item['tags']:
                item['tags'].append(it)

    item['summary'] = content_json['description']

    item['content_html'] = ''
    if content_json.get('attachments') and content_json['attachments'].get('main_image'):
        item['_image'] = resize_image(content_json['attachments']['main_image']['src'])
        if content_json['attachments']['main_image']['description'] == 'N/A':
            caption = ''
        else:
            caption = content_json['attachments']['main_image']['description']
        item['content_html'] += utils.add_image(item['_image'], caption)
    if content_json.get('embed_url'):
        item['content_html'] = utils.add_embed(content_json['embed_url'])

    body = ''
    if content_json.get('body'):
        body += content_json['body']
    elif content_json.get('body_parts'):
        for it in content_json['body_parts']:
            body += it
    if content_json.get('paywall_parts'):
        body += content_json['paywall_parts']
    soup = BeautifulSoup(body, 'html.parser')

    for el in soup.find_all('figure'):
        img = el.find('img')
        if img:
            captions = []
            figcap = el.find('figcaption')
            for it in figcap.find_all('div'):
                captions.append(it.get_text().strip())
            if not captions:
                captions.append(figcap.get_text().strip())
            new_html = utils.add_image(resize_image(img['src']), ' '.join(captions))
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled figure in ' + item['url'])

    for el in soup.find_all(class_='embed-responsive'):
        it = el.find('iframe')
        if it:
            new_html = utils.add_embed(it['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled embed-responsive in ' + item['url'])

    for el in soup.find_all('a', class_=True):
        del el['class']

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_json = get_next_json(args['url'])
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/feed.json')

    feed = utils.init_jsonfeed(args)

    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        articles = next_json['pageProps']['pageData']['latests']
        feed['title'] = 'Interesting Engineering'
    elif len(paths) == 1:
        articles = next_json['pageProps']['categoryResults']
        feed['title'] = 'Interesting Engineering | ' + next_json['pageProps']['categoryName'].title()
    elif paths[0] == 'author':
        articles = next_json['pageProps']['articlesData']
        feed['title'] = 'Interesting Engineering | {} {}'.format(next_json['pageProps']['userData']['name'], next_json['pageProps']['userData']['surname'])

    feed_items = []
    for article in articles:
        url = 'https://interestingengineering.com/' + article['url']
        if next((it for it in feed_items if it['url'] == url), None):
            logger.debug('skipping duplicate url')
            continue
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)

    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed


def test_handler():
    feeds = ['https://interestingengineering.com/',
             'https://interestingengineering.com/innovation',
             'https://interestingengineering.com/author/can-emir/page/1',
             'https://interestingengineering.com/video']
    for url in feeds:
        get_feed({"url": url}, True)
