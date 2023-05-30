import html, json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def add_image(image, heading='', desc=''):
    img_src = image['resize_url'] + '&size=responsive970'
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('credit'):
        captions.append(image['credit'])
    if heading:
        heading = '<div style="text-align:center; font-size:1.2em; font-weight:bold">{}</div>'.format(heading)
    return utils.add_image(img_src, ' | '.join(captions), heading=heading, desc=desc)


def get_content(url, args, site_json, save_debug=False, module_format_content=None):
    if '/live-events' in url:
        return None

    page_json = utils.get_url_json(utils.clean_url(url) + '?renderer=json')
    if not page_json:
        return None
    if save_debug:
        utils.write_file(page_json, './debug/debug.json')

    if page_json.get('topic'):
        article_json = page_json['topic']
    else:
        article_json = page_json

    item = get_item(article_json, args, site_json, save_debug)
    if page_json.get('articles'):
        for article in page_json['articles']:
            add_item = get_item(article, args, site_json, save_debug)
            item['content_html'] += '<hr/><h2>{}</h2><p>by {}<br/>{}</p>{}'.format(add_item['title'], add_item['author']['name'], add_item['_display_date'], add_item['content_html'])
    return item


def get_item(article_json, args, site_json, save_debug):
    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['permalink']
    item['title'] = article_json['headline']

    if article_json.get('original_publish_date'):
        dt = datetime.fromisoformat(article_json['original_publish_date'].replace('Z', '+00:00'))
    elif article_json.get('taggable_publish_date'):
        dt = datetime.fromisoformat(article_json['taggable_publish_date'].replace('Z', '+00:00'))

    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['update_date_for_export'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    authors = []
    for it in article_json['authors']:
        authors.append(it['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if article_json.get('meta') and article_json['meta'].get('keywords'):
        item['tags'] = re.split(r'(?<=\w),(?=\w)', article_json['meta']['keywords'])
    elif article_json.get('tags'):
        for it in article_json['tags']:
            item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''
    if article_json.get('deck'):
        item['summary'] = article_json['deck']
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['deck'])

    if article_json.get('image'):
        item['_image'] = article_json['image']['resize_url'] + '&size=responsive970'
        item['content_html'] += add_image(article_json['image'])

    if article_json.get('body'):
        for body in article_json['body']:
            if isinstance(body, str):
                item['content_html'] += body
            elif isinstance(body, dict):
                if body.get('template'):
                    if re.search(r'/ads/|gallery-enhancement|related-link', body['template']):
                        continue
                    elif '/image-enhancement' in body['template']:
                        if body.get('alignment') and (body['alignment'] == 'right' or body['alignment'] == 'left'):
                            continue
                        else:
                            item['content_html'] += add_image(body)
                    else:
                        logger.warning('unhandled body template {} in {}'.format(body['template'], item['url']))
                elif body.get('macro') and body['macro'] == 'slideshow_builder':
                    continue
                else:
                    logger.warning('unhandled body section ' + item['url'])
    elif article_json.get('args') and article_json['args'].get('slides'):
        for i, slide in enumerate(article_json['args']['slides']):
            if slide.get('image'):
                if i == 0 and not item.get('_image'):
                    item['_image'] = slide['image']['resize_url'] + '&size=responsive970'
                desc = ''
                heading = ''
                if slide.get('caption'):
                    desc = '<p>{}</p>'.format(slide['caption'])
                if slide.get('title'):
                    heading = slide['title']
                if slide.get('lead'):
                    for it in slide['lead']:
                        desc += it
                item['content_html'] += add_image(slide['image'], heading, desc)

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    page_json = utils.get_url_json(utils.clean_url(url) + '?renderer=json')
    if not page_json:
        return None
    if save_debug:
        utils.write_file(page_json, './debug/feed.json')

    def get_items_urls(items):
        urls = []
        for item in items:
            if item.get('items'):
                urls += get_items_urls(item['items'])
            elif item.get('permalink'):
                urls.append(item['permalink'])
        return urls

    # removes duplicates
    article_urls = []
    if page_json.get('main'):
        article_urls = [*set(get_items_urls(page_json['main']['items']))]
    elif page_json.get('buckets'):
        for bucket in page_json['buckets']:
            if bucket.get('items') and bucket['items'].get('items'):
                article_urls += get_items_urls(bucket['items']['items'])
        article_urls = [*set(article_urls)]

    n = 0
    feed_items = []
    for article_url in article_urls:
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
    #feed['title'] = soup.title.get_text()
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
