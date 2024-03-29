import json, re, tldextract
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    return utils.clean_url(img_src) + '?width=1000&quality=80&format=webply'


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
    if site_json.get('assetPrefix'):
        next_url = '{}/_next/data/{}{}'.format(site_json['assetPrefix'], site_json['buildId'], path)
    else:
        next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'html.parser')
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
    return get_item(next_data['pageProps']['data']['result'], args, site_json, save_debug)


def get_item(article_json, args, site_json, save_debug):
    item = {}
    item['id'] = article_json['uid']
    item['url'] = '{}/{}{}'.format(site_json['site_href'], article_json['term_selector']['primaryTerm'], article_json['url'])
    item['title'] = BeautifulSoup(article_json['title'], 'html.parser').text

    dt = datetime.fromisoformat(article_json['published_date'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['updated_at'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in article_json['author_page']:
        authors.append(it['author_name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json.get('term_selector'):
        item['tags'] = []
        item['tags'].append(article_json['term_selector']['primaryTerm'])
        if article_json['term_selector'].get('secondaryTerm'):
            for it in article_json['term_selector']['secondaryTerm']:
                item['tags'].append(it)

    item['content_html'] = ''
    if article_json.get('summary'):
        item['summary'] = article_json['summary']
        item['content_html'] += '<p><em>{}</p></em>'.format(item['summary'])

    if article_json.get('featured_image'):
        item['_image'] = resize_image(article_json['featured_image']['url'])
        captions = []
        if article_json.get('featured_image_caption'):
            captions.append(article_json['featured_image_caption'])
        if article_json.get('featured_image_credit'):
            captions.append(article_json['featured_image_credit'])
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    soup = BeautifulSoup(article_json['body'], 'html.parser')
    for el in soup.find_all('figure'):
        img_src = ''
        it = el.find('img')
        if it and it.get('src'):
            img_src = resize_image(it['src'])
        else:
            it = el.find('source')
            if it:
                img_src = resize_image(it['srcSet'])
        it = el.find('figcaption')
        if it:
            caption = it.string
        else:
            caption = ''
        if img_src:
            new_html = utils.add_image(img_src, caption)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled figure in ' + item['url'])

    for el in soup.find_all('img', attrs={"data-image": True}):
        new_html = utils.add_image(resize_image(el['src']))
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('blockquote', class_='twitter-tweet'):
        links = el.find_all('a')
        new_html = utils.add_embed(links[-1]['href'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(attrs={"style": "font-size: 11pt;"}):
        if el.name == 'span':
            el.unwrap()
        else:
            el.attrs = {}

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    # Site feed: https://www.gamedeveloper.com/rss.xml
    # Author feed: https://www.gamedeveloper.com/rss.xml?a=bryant-francis
    if 'rss.xml' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    next_data = get_next_data(args['url'])
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    split_url = urlsplit(url)
    n = 0
    feed_items = []
    if next_data['pageProps']['data'].get('contents'):
        for article in next_data['pageProps']['data']['contents']:
            article_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, article['fullUrl'])
            if save_debug:
                logger.debug('getting content for ' + article_url)
            if article.get('body'):
                item = get_item(article, args, site_json, save_debug)
            else:
                item = get_content(article_url, args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break
    elif next_data['pageProps']['data'].get('dataStandardViewInit'):
        for it in next_data['pageProps']['data']['dataStandardViewInit']['items']:
            article = it['_source']
            article_url = '{}://{}/{}{}'.format(split_url.scheme, split_url.netloc, article['term_selector']['primaryTerm'], article['url'])
            if save_debug:
                logger.debug('getting content for ' + article_url)
            if article.get('body'):
                item = get_item(article, args, site_json, save_debug)
            else:
                item = get_content(article_url, args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

    feed = utils.init_jsonfeed(args)
    if next_data['pageProps']['data'].get('labelInfo'):
        feed['title'] = '{} | {}'.format(next_data['pageProps']['data']['labelInfo']['title'], split_url.netloc)
    elif next_data['pageProps']['data'].get('tagManagerArgs'):
        feed['title'] = '{} | {}'.format(next_data['pageProps']['data']['tagManagerArgs']['dataLayer']['pageTitle'], split_url.netloc)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed