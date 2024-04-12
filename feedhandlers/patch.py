import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index.json'
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
        path += '.json'

    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
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
    utils.write_file(next_data, './debug/debug.json')

    content_json = next_data['pageProps']['mainContent']['item']
    item = {}
    item['id'] = content_json['id']
    item['url'] = 'https://patch.com' + content_json['canonicalUrl']
    item['title'] = content_json['title']

    dt = datetime.fromisoformat(content_json['created'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if content_json.get('updated'):
        dt = datetime.fromisoformat(content_json['updated'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {"name": content_json['author']['name']}

    item['tags'] = []
    if content_json.get('category'):
        item['tags'].append(content_json['category'])
    if content_json.get('topic'):
        item['tags'].append(content_json['topic']['name'])
    if content_json.get('tags'):
        for it in content_json['tags']:
            item['tags'].append(it['name'])
    if content_json.get('contentKeywords'):
        item['tags'] += content_json['contentKeywords']

    item['content_html'] = ''
    if content_json.get('summary'):
        item['summary'] = content_json['summary']
        item['content_html'] += '<p><em>' + content_json['summary'] + '</em></p>'

    if content_json.get('preHeader'):
        item['summary'] = content_json['preHeader']

    if content_json.get('video'):
        if 'iframe' in content_json['video']:
            m = re.search(r'src="([^"]+)"', content_json['video'])
            if m:
                item['content_html'] += utils.add_embed(m.group(1))
                if content_json.get('imageThumbnail'):
                    item['_image'] = content_json['imageThumbnail']
            else:
                logger.warning('unhandled video iframe in ' + item['url'])
        else:
            logger.warning('unhandled video block in ' + item['url'])
    elif content_json.get('images'):
        item['_image'] = content_json['images'][0]['url']
        captions = []
        if content_json['images'][0].get('caption'):
            captions.append(content_json['images'][0]['caption'])
        if content_json['images'][0].get('credit'):
            captions.append(content_json['images'][0]['credit'])
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))
    elif content_json.get('imageThumbnail'):
        item['_image'] = content_json['imageThumbnail']
        item['content_html'] += utils.add_image(item['_image'])

    for block in content_json['contentBlocks']:
        if block['type'] == 'advertisement' or block['type'] == 'recirc' or block['type'] == 'subscribe':
            continue
        elif block['type'] == 'html':
            if '<iframe' in block['content']:
                soup = BeautifulSoup(block['content'], 'html.parser')
                el = soup.find('iframe')
                if el.get('src'):
                    new_html = utils.add_embed(el['src'])
                elif el.get('data-src'):
                    new_html = utils.add_embed(el['data-src'])
                el.replace_with(BeautifulSoup(new_html, 'html.parser'))
                item['content_html'] += str(soup)
            else:
                item['content_html'] += block['content']
        else:
            logger.warning('unhandled content block {} in {}'.format(block['type'], item['url']))

    if re.search(r'doubleclick|adsafeprotected', item['content_html']):
        soup = BeautifulSoup(item['content_html'], 'html.parser')
        for el in soup.find_all('a', href=re.compile(r'doubleclick|adsafeprotected')):
            link = utils.get_redirect_url(el['href'])
            if link == el['href']:
                el.unwrap()
            else:
                el['href'] = link
        for el in soup.find_all('img', attrs={"data-src": re.compile(r'doubleclick|adsafeprotected')}):
            el.decompose()
        item['content_html'] = str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    utils.write_file(next_data, './debug/feed.json')

    feed_items = []
    for article in next_data['pageProps']['mainContent']['newsfeed']:
        if article['type'] != 'article' or article['category'] == 'sponsored':
            continue
        article_url = 'https://patch.com' + article['canonicalUrl']
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_content(article_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)

    # This gets local social media posts
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) == 2:
        local_stream = get_next_data(url + '/localstream', site_json)
        for article in local_stream['pageProps']['mainContent']:
            if article['type'] != 'social':
                continue
            if save_debug:
                logger.debug('getting content for ' + article['itemAlias'])
            item = utils.get_content(article['itemAlias'], {})
            if item:
                if not item.get('_timestamp'):
                    dt = datetime.fromisoformat(article['created'])
                    item['date_published'] = dt.isoformat()
                    item['_timestamp'] = dt.timestamp()
                    item['_display_date'] = utils.format_display_date(dt)
                    if article.get('updated'):
                        dt = datetime.fromisoformat(article['updated'])
                        item['date_modified'] = dt.isoformat()
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)

    feed = utils.init_jsonfeed(args)
    feed['title'] = next_data['pageProps']['metadata']['pageTitle']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
