import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import semafor

import logging

logger = logging.getLogger(__name__)


def resize_image(image, width=1200):
    return utils.clean_url(image['src']) + 'w={}&q=70&auto=format&dpr=1'.format(width)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    query = ''
    if len(paths) == 0:
        path = '/index.json'
    else:
        path = split_url.path
        if path.endswith('/'):
            path = path[:-1]
        path += '.json'
        if paths[0] == 'sections':
            query += '?sectionSlug={}'.format(paths[1])
        if 'contributors' in paths:
            query += '?slug={}'.format(paths[1])
        if 'articles' in paths:
            query += '&slug={}'.format(paths[3])
    next_url = '{}://{}/_next/data/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, query)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if el:
            next_data = json.loads(el.string)
            if paths[0] != 'hfm' and next_data['buildId'] != site_json['buildId']:
                site_json['buildId'] = next_data['buildId']
                utils.update_sites(url, site_json)
            next_data = next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')
    article_json = next_data['pageProps']['article']

    item = {}
    item['id'] = article_json['id']
    item['url'] = url
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['meta']['createdAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['meta']['updatedAt'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in article_json['meta']['authors']:
        authors.append('{} {}'.format(it['firstName'], it['lastName']))
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json['meta'].get('tags'):
        item['tags'] = []
        for it in article_json['meta']['tags']:
            item['tags'].append(it['title'])

    item['content_html'] = ''
    if article_json['hero'].get('dek'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['hero']['dek'])

    if article_json['hero'].get('heroImage'):
        item['_image'] = article_json['hero']['heroImage']['src']
        item['content_html'] += semafor.add_image(article_json['hero']['heroImage'], resize_image)

    for block in article_json['content']['body']:
        item['content_html'] += semafor.render_block(block)

    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    articles = []
    section = None
    if len(paths) == 0:
        section = next_data['pageProps']['frontPage']
    elif 'sections' in paths:
        section = next_data['pageProps']['currentSection']
    elif 'contributors' in paths:
        articles = next_data['pageProps']['contributorArticles']['items']

    if section:
        for module in section['modules']:
            for key, val in module.items():
                if key.startswith('article') and isinstance(val, dict) and val.get('_type') and val['_type'] == 'article':
                    articles.append(val)

    n = 0
    feed_items = []
    for article in articles:
        article_url = 'https://www.tabletmag.com/sections/{}/articles/{}'.format(article['section']['slug'], article['slug'])
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_content(article_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    #feed['title'] = 'Semafor'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
    return None
