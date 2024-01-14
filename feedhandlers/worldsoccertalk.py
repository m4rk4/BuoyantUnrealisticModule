import json, math, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    split_url = urlsplit(img_src)
    params = parse_qs(split_url.query)
    if split_url.netloc == 'ds-images.bolavip.com' and params.get('width') and params.get('height'):
        n = width / int(params['width'][0])
        height = math.floor(n * int(params['height'][0]))
        params['width'][0] = width
        params['height'][0] = height
        img_src = '{}://{}{}?{}'.format(split_url.scheme, split_url.netloc, split_url.path, urlencode(params, doseq=True))
    return img_src


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
    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    if len(paths) > 0:
        if paths[0] == 'tag':
            next_url += '?tagId=' + paths[1]
        elif paths[0] == 'category':
            next_url += '?params=' + paths[1]
        elif paths[0] == 'author':
            next_url += '?username=' + paths[1]
        else:
            next_url += '?pathSegments=' + '&pathSegments='.join(paths)
    # print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        if page_html:
            soup = BeautifulSoup(page_html, 'lxml')
            el = soup.find('script', id='__NEXT_DATA__')
            if el:
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
    return get_item(next_data['pageProps']['article'], args, site_json, save_debug)


def get_item(article_json, args, site_json, save_debug):
    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['canonical']
    item['title'] = article_json['title']

    if article_json.get('publishedAt'):
        dt = datetime.fromisoformat(article_json['publishedAt']).astimezone(timezone.utc)
    elif article_json.get('published_at'):
        dt = datetime.fromisoformat(article_json['published_at']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('modifiedAtRef'):
        dt = datetime.fromisoformat(article_json['modifiedAtRef']).astimezone(timezone.utc)
    elif article_json.get('modified_at'):
        dt = datetime.fromisoformat(article_json['modified_at']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in article_json['author']:
        authors.append(it['name'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if article_json.get('categories'):
        for it in article_json['categories']:
            if it['categoryName'] not in item['tags']:
                item['tags'].append(it['categoryName'])
    if article_json.get('tags'):
        for it in article_json['tags']:
            if it['text'] not in item['tags']:
                item['tags'].append(it['text'])

    if article_json.get('excerpt'):
        item['summary'] = article_json['excerpt']

    item['content_html'] = ''
    if article_json.get('images'):
        item['_image'] = article_json['images']['full']
        item['content_html'] += utils.add_image(resize_image(item['_image']), article_json.get('credits'))

    soup = BeautifulSoup(article_json['body'], 'html.parser')
    for el in soup.find_all('figure', class_=['wp-block-image', 'image']):
        if el.name == None:
            continue
        it = el.find('img')
        if it:
            img_src = resize_image(it['src'])
            it = el.find('a')
            if it:
                link = it['href']
            else:
                link = ''
            # TODO: captions
            new_html = utils.add_image(img_src, link=link)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled image in ' + item['url'])

    for el in soup.find_all(class_='wp-block-embed'):
        new_html = ''
        if 'wp-block-embed-twitter' in el['class']:
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])
        elif 'wp-block-embed-youtube' in el['class']:
            it = el.find('iframe')
            new_html = utils.add_embed(it['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled wp-block-embed in ' + item['url'])

    for el in soup.find_all(class_='wp-block-code'):
        new_html = ''
        it = el.find('iframe')
        if it:
            new_html = utils.add_embed(it['src'])
        elif el.find('blockquote', class_='twitter-tweet'):
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled wp-block-code in ' + item['url'])

    for el in soup.find_all('h5'):
        el.name = 'h4'

    for el in soup.find_all('div', recursive=False):
        el.name = 'p'

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    if '/rss/' in url:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    n = 0
    feed_items = []
    for article in next_data['pageProps']['posts']:
        if save_debug:
            logger.debug('getting content for ' + article['url'])
        if article.get('body'):
            item = get_item(article, args, site_json, save_debug)
        else:
            item = get_content(article['url'], args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    #feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
