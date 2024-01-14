import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if split_url.netloc == 'matchcentre.liverpoolfc.com':
        return None
    api_url = site_json['api_path'] + split_url.path
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    item = {}
    item['id'] = api_json['id']
    item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, api_json['url'])
    item['title'] = api_json['title']

    dt = datetime.fromisoformat(api_json['publishedAt'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(api_json['updatedAt'])
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if api_json.get('author'):
        logger.warning('unhandled authors in ' + item['url'])
    elif api_json.get('metaDescription') and api_json['metaDescription'].startswith('By '):
        item['author']['name'] = re.sub(r'^By ', '', api_json['metaDescription'])

    if api_json.get('tags'):
        item['tags'] = api_json['tags'].copy()

    if api_json.get('seoDescription'):
        item['summary'] = api_json['seoDescription']

    item['content_html'] = ''
    if api_json.get('byline'):
        item['content_html'] += '<p><em>{}</em></p>'.format(api_json['byline'])

    if api_json.get('coverImage'):
        image = utils.closest_dict(api_json['coverImage']['sizes'].values(), 'width', 1200)
        item['_image'] = image['url']
        item['content_html'] += utils.add_image(item['_image'])

    for block in api_json['blocks']:
        if block['type'] == 'formattedText':
            item['content_html'] += block['formattedText']
        elif block['type'] == 'image':
            image = utils.closest_dict(block['image']['sizes'].values(), 'width', 1200)
            # TODO: captions
            item['content_html'] += utils.add_image(image['url'])
        elif block['type'] == 'youtubeVideo':
            item['content_html'] += utils.add_embed('https://www.youtube.com/watch?v=' + block['youtubeID'])
        elif block['type'] == 'socialEmbed':
            if block['socialMediaChannel'] == 'instagram':
                item['content_html'] += utils.add_embed('https://www.instagram.com/p/{}/'.format(block['resource']))
            else:
                logger.warning('unhandled socialEmbed channel {} in {}'.format(block['socialMediaChannel'], item['url']))
        elif block['type'] == 'monterosaEmbed':
            item['content_html'] += utils.add_embed(block['url'])
        elif block['type'] == 'relatedArticles':
            pass
        else:
            logger.warning('unhandled block type {} in {}'.format(block['type'], item['url']))
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    api_url = site_json['api_path'] + split_url.path
    if split_url.query:
        api_url += '?' + split_url.query + '&perPage=10'
    else:
        api_url += '?perPage=10'
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    feed_items = []
    for article in api_json['results']:
        article_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, article['url'])
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
    # feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
