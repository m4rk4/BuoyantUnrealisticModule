import base64, json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    path += '.json'
    if len(paths) == 5:
        query = '?tag={}&slug={}&uuid={}'.format(paths[2], paths[3], paths[4])
    else:
        query = ''
    next_url = '{}/_next/data/{}{}{}'.format(site_json['articleApiEndpoint'], site_json['buildId'], path, query)
    print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if not el:
            logger.warning('unable to find __NEXT_DATA__ in ' + url)
            return None
        next_data = json.loads(el.string)
        if next_data['buildId'] != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = next_data['buildId']
            utils.update_sites(url, site_json)
        return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')
    page_json = next_data['pageProps']

    item = {}
    item['id'] = page_json['uuid']
    item['url'] = page_json['url']
    item['title'] = page_json['headline']

    dt = datetime.fromisoformat(page_json['publishedTime'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(page_json['lastUpdateTime'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    authors = []
    if page_json.get('authors'):
        for it in page_json['authors']:
            authors.append(it['name'])
    elif page_json.get('byLine'):
        authors.append(page_json['byLine'])
    elif page_json.get('outlet'):
        authors.append(page_json['outlet'])
    if authors:
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if page_json.get('articleTag'):
        item['tags'] = [page_json['articleTag']]

    item['content_html'] = ''
    if page_json.get('teaser'):
        item['summary'] = page_json['teaser']
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    if page_json.get('image'):
        item['_image'] = page_json['image']['url']
        item['content_html'] += utils.add_image(item['_image'])

    soup = BeautifulSoup(page_json['body'], 'html.parser')
    for el in soup.find_all('blockquote', class_='twitter-tweet'):
        links = el.find_all('a')
        new_html = utils.add_embed(links[-1]['href'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(id=['gtx-trans', 'UMS_TOOLTIP']):
        el.decompose()

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    split_url = urlsplit(url)

    n = 0
    feed_items = []
    for tile in next_data['pageProps']['Tiles']:
        uuid = tile['Id'].split(':')
        article_url = '{}://{}/{}/{}/{}/{}/{}'.format(split_url.scheme, split_url.netloc, next_data['pageProps']['dazn']['locale'], uuid[0].lower(), tile['UrlTag'], tile['Slug'], uuid[1])
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
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
