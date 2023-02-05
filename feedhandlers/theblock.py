import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if paths[0] == 'data':
        if paths[-1] == 'embed':
            del paths[-1]
        api_url = 'https://www.theblock.co/api/charts/chart/' + '/'.join(paths[1:])
    elif 'theblockcrypto.com' in split_url.netloc:
        api_url = 'https://www.theblockcrypto.com/wp-json/v1/post/' + paths[1]
    else:
        api_url = '{}://{}/api/post/{}'.format(split_url.scheme, split_url.netloc, paths[1])
    api_json = utils.get_url_json(api_url)
    if not api_url:
        return None
    if '/chart/' in api_url:
        post_json = api_json['chart']
    else:
        post_json = api_json['post']
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['id']
    item['url'] = post_json['url']
    item['title'] = post_json['title']

    if post_json['type'] == 'chart':
        dt = datetime.strptime(post_json['lastUpdated'], '%Y-%m-%d %H:%M:%S').astimezone(timezone.utc)
    else:
        dt = datetime.fromisoformat(post_json['published']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    # TODO: modified is not isoformat
    # if post_json.get('modified'):
    #     dt = datetime.fromisoformat(post_json['modified']).astimezone(timezone.utc)
    #     item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if post_json.get('authors'):
        authors = []
        for it in post_json['authors']:
            authors.append(it['name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author']['name'] = 'The Block'

    item['tags'] = []
    if post_json.get('primaryCategory'):
        item['tags'].append(post_json['primaryCategory']['name'])
    if post_json.get('categories'):
        for it in post_json['categories']:
            item['tags'].append(it['name'])
    if post_json.get('tags'):
        for it in post_json['tags']:
            item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    if post_json.get('excerpt'):
        item['summary'] = post_json['excerpt']

    item['content_html'] = ''

    if post_json['type'] == 'chart' and 'embed.' in split_url.netloc:
        caption = '<a href="{}">{}</a>'.format(item['url'], item['title'])
        item['content_html'] += utils.add_image(post_json['thumbnail'], caption)
        return item

    if post_json.get('intro'):
        item['content_html'] += post_json['intro']

    if post_json.get('thumbnail'):
        item['_image'] = post_json['thumbnail']
        captions = []
        if post_json.get('thumbnailCaption'):
            captions.append(post_json['thumbnailCaption'])
        if post_json.get('thumbnailCredit'):
            soup = BeautifulSoup(post_json['thumbnailCredit'], 'html.parser')
            for el in soup.find_all('span'):
                el.unwrap()
            captions.append(str(soup))
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    soup = BeautifulSoup(post_json['body'], 'html.parser')
    for el in soup.find_all(class_='wp-caption'):
        img = el.find('img')
        if img:
            caption = el.find(class_='wp-caption-text')
            if caption:
                for it in caption.find_all('span'):
                    it.unwrap()
                caption = caption.decode_contents()
            else:
                caption = ''
            new_el = BeautifulSoup(utils.add_image(img['src'], caption), 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled wp-caption in ' + item['url'])

    for el in soup.find_all('iframe'):
        new_el = BeautifulSoup(utils.add_embed(el['src']), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path.split('/')))

    api_json = ''
    if len(paths) == 0:
        api_url = 'https://www.theblock.co/api/home'
        api_json = utils.get_url_json(api_url)
        if not api_url:
            return None
        posts = api_json['latest']['posts']
    elif len(paths) == 1:
        api_url = 'https://www.theblock.co/api/pagesPlus/data/{}/1'.format(paths[0])
        api_json = utils.get_url_json(api_url)
        if not api_url:
            return None
        posts = api_json[paths[0]]['posts']
    elif paths[0] == 'category':
        api_url ='https://www.theblock.co/api' + split_url.path
        api_json = utils.get_url_json(api_url)
        if not api_url:
            return None
        posts = api_json['data']['articles']

    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    feed_items = []
    for post in posts:
        if '/report/' in post['url'] and post.get('cta') and post['cta'].get('url'):
            url = post['cta']['url']
        else:
            url = post['url']
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    if api_json.get('name'):
        feed['title'] = 'The Block | ' + api_json['name']
    elif api_json.get('pageData'):
        feed['title'] = 'The Block | ' + api_json['pageData']['title']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
