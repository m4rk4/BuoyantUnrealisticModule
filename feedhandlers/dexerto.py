import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    return 'https://www.dexerto.com/cdn-cgi/image/width={},quality=75,format=auto/{}'.format(width, img_src)


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
    #print(next_url)
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
    article_json = next_data['pageProps']['article']
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    item = {}
    item['id'] = article_json['id']
    item['url'] = 'https://' + split_url.netloc + article_json['href']
    item['title'] = article_json['heading']

    dt = datetime.fromisoformat(article_json['timePublished']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['timeUpdated']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {"name": article_json['author']['name']}

    item['tags'] = []
    item['tags'].append(article_json['category']['name'])
    if article_json.get('secondaryCategories'):
        for it in article_json['secondaryCategories']:
            item['tags'].append(it['name'])
    if article_json.get('tags'):
        for it in article_json['tags']:
            item['tags'].append(it['name'])

    item['content_html'] = ''
    if article_json.get('product') and article_json['product'].get('rating'):
        item['content_html'] += '<p style="font-size:1.5em; font-weight:bold;">Rating: '
        for i in range(5):
            if i < article_json['product']['rating']:
                item['content_html'] += '★'
            else:
                item['content_html'] += '☆'
        item['content_html'] += '</p>'

    if article_json.get('img'):
        item['_image'] = article_json['img']['src']
        captions = []
        if article_json['img'].get('caption'):
            captions.append(article_json['img']['caption'])
        if article_json['img'].get('credits'):
            captions.append(article_json['img']['credits'])
        item['content_html'] += utils.add_image(resize_image(item['_image']), ' | '.join(captions))

    if article_json.get('description'):
        item['summary'] = article_json['description']

    soup = BeautifulSoup(article_json['content']['rendered'], 'html.parser')
    for el in soup.find_all(attrs={"data-placeholder": ["ad", "ad-lite", "mid-article-widget", "player"]}):
        el.decompose()

    for el in soup.find_all('figure'):
        new_html = ''
        el_parent = None
        if el.get('class') and 'wp-block-embed' in el['class']:
            if 'wp-block-embed-twitter' in el['class']:
                links = el.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
            elif 'wp-block-embed-tiktok' in el['class']:
                it = el.find('blockquote')
                if it:
                    new_html = utils.add_embed(it['cite'])
            elif 'wp-block-embed-youtube' in el['class']:
                it = el.find('iframe')
                if it:
                    new_html = utils.add_embed(it['src'])
        else:
            img = el.find('img')
            if img:
                if img.get('srcset'):
                    img_src = utils.image_from_srcset(img['srcset'], 1200)
                else:
                    img_src = resize_image(img['src'])
                captions = []
                it = el.find('figcaption')
                if it:
                    captions.append(it.get_text())
                if el.parent and el.parent.get('class') and 'caption' in el.parent['class']:
                    el_parent = el.parent
                    el.decompose()
                    captions.insert(0, el_parent.decode_contents())
                new_html = utils.add_image(img_src, ' | '.join(captions))
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            if el_parent:
                el_parent.insert_after(new_el)
                el_parent.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()
        else:
            logger.warning('unhandled figure in ' + item['url'])

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    split_url = urlsplit(url)
    n = 0
    feed_items = []
    for post in next_data['pageProps']['vertical']['posts']:
        post_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, post['href'])
        if save_debug:
            logger.debug('getting content for ' + post_url)
        item = get_content(post_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['title'] = next_data['pageProps']['vertical']['seo']['title']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
