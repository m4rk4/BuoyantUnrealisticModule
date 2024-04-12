import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit, unquote_plus

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Chromium\";v=\"122\", \"Not(A:Brand\";v=\"24\", \"Microsoft Edge\";v=\"122\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-language": "en",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
    }
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    headers['user-language'] = paths[0]
    api_url = 'https://api.theins.info/posts/{}?rubrics={}'.format(paths[-1], paths[1])
    article_json = utils.get_url_json(api_url, headers=headers)
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = url
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['date_from'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    authors = []
    for it in article_json['authors']:
        authors.append(it['full_name'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json.get('tags'):
        logger.warning('unhandled tags in ' + item['url'])

    if article_json['meta'].get('keywords'):
        logger.warning('unhandled keywords in ' + item['url'])

    if article_json['meta'].get('image'):
        item['_image'] = article_json['meta']['image']

    if article_json['meta'].get('description'):
        item['summary'] = article_json['meta']['description']

    item['content_html'] = ''

    if article_json.get('lead'):
        item['content_html'] += '<p><em>' + re.sub(r'</?p>|<br>', '', article_json['lead']) + '</em></p>'

    if article_json.get('detail_image'):
        captions = []
        if article_json['detail_image'].get('caption'):
            captions.append(article_json['detail_image']['caption'])
        if article_json['detail_image'].get('credit'):
            captions.append(article_json['detail_image']['credit'])
        # TODO: resize
        item['content_html'] += utils.add_image(article_json['detail_image']['original'], ' | '.join(captions))

    for block in article_json['blocks']:
        if block['kind'] == 'text':
            item['content_html'] += block['text'].replace('</blockquote><blockquote>', '<br/><br/>').replace('<blockquote>', '<blockquote style="border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;">')
        elif block['kind'] == 'image' or block['kind'] == 'gallery':
            for it in block['images']:
                captions = []
                if it.get('caption'):
                    captions.append(it['caption'])
                if it.get('credit'):
                    captions.append(it['credit'])
                # TODO: resize
                item['content_html'] += utils.add_image(it['original'], ' | '.join(captions))
        elif block['kind'] == 'video':
            if block.get('url'):
                item['content_html'] += utils.add_embed(block['url'])
            else:
                logger.warning('unhandled video block in ' + item['url'])
        elif block['kind'] == 'quote':
            # TODO: attribution?
            item['content_html'] += utils.add_pullquote(block['quote'])
        elif block['kind'] == 'social':
            if block['social_type'] == 'twitter':
                if block['social_embed'].startswith('http'):
                    item['content_html'] += utils.add_embed(block['social_embed'])
                else:
                    m = re.findall(r'href="([^"]+)"', block['social_embed'])
                    item['content_html'] += utils.add_embed(m[-1])
            elif block['social_type'] == 'telegram':
                item['content_html'] += utils.add_embed(block['social_embed'])
            else:
                logger.warning('unhandled social block {} in {}'.format(block['social_type'], item['url']))
        elif block['kind'] == 'related_posts':
            continue
        else:
            logger.warning('unhandled block kind {} in {}'.format(block['kind'], item['url']))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Chromium\";v=\"122\", \"Not(A:Brand\";v=\"24\", \"Microsoft Edge\";v=\"122\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-language": "en",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
    }
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    headers['user-language'] = paths[0]
    if paths[1] == 'opinion' and len(paths) == 3:
        api_url = 'https://api.theins.info/rubric-posts?limit=10&columnist_list%5B%5D=' + paths[2]
    else:
        api_url = 'https://api.theins.info/rubrics/{}?limit=10'.format(paths[1])
    api_json = utils.get_url_json(api_url, headers=headers)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    if api_json.get('posts'):
        posts = api_json['posts']['items']
    elif api_json.get('items'):
        posts = api_json['items']
    else:
        logger.warning('no feed posts found in ' + api_url)
        return None

    n = 0
    feed_items = []
    for post in posts:
        post_url = 'https://theins.ru/{}/{}/{}'.format(headers['user-language'], post['rubrics'][0]['slug'], post['slug'])
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
    if api_json.get('title'):
        feed['title'] = api_json['title'] + ' | theins.ru'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
