import json, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    split_url = urlsplit(img_src)
    paths = list(filter(None, split_url.path.split('/')))
    return 'https://images.deadspin.com/tr:w-{}/{}'.format(width, paths[-1])


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    else:
        path = split_url.path
        if path.endswith('/'):
            path = path[:-1]
    next_url = '{}://{}/_next/data/{}/{}.json'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    #print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
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

    page_json = next_data['pageProps']
    item = {}
    item['id'] = page_json['article']['name']
    item['url'] = url
    item['title'] = page_json['article']['friendlyName']

    dt = dateutil.parser.parse(re.sub(r' \([^\)]+\)$', '', page_json['article']['createdAt']))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, date_only=True)
    if page_json['article'].get('updatedAt'):
        dt = dateutil.parser.parse(re.sub(r' \([^\)]+\)$', '', page_json['article']['updatedAt']))
        item['date_modified'] = dt.isoformat()

    item['author'] = {
        "name": page_json['author']['name']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    if page_json['article'].get('tag'):
        item['tags'] = []
        for it in json.loads(page_json['article']['tag']):
            if isinstance(it, str):
                item['tags'].append(it)
            elif isinstance(it, dict):
                item['tags'].append(it['displayName'])

    if page_json.get('pic'):
        item['image'] = resize_image(page_json['pic'])

    if page_json['article'].get('seoMeta'):
        item['summary'] = page_json['article']['seoMeta']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    def render_content(content):
        content_html = ''
        content_type = content['type'].lower()
        if content_type == 'text':
            content_html += content['value']
        elif content_type == 'image':
            captions = []
            if content.get('caption'):
                caption = ''
                for it in content['caption']:
                    caption += render_content(it)                
                captions.append(caption)
            if content.get('source'):
                caption = ''
                for it in content['source']:
                    caption += render_content(it)                
                captions.append(caption)
            content_html += utils.add_image(resize_image(content['newUrl']), ' | '.join(captions))
        elif content_type == 'fullimage':
            content_html += utils.add_image(resize_image(content['newUrl']), content.get('caption'))
        elif content_type == 'twitter':
            content_html += utils.add_embed('https://twitter.com/_/status/{}'.format(content['id']))
        elif content_type == 'sportsbettingsingleoption' or content_type == 'RelatedItemsList':
            pass
        else:
            logger.warning('unhandled content type ' + content['type'])
        return content_html

    item['content_html'] = ''
    for content in page_json['article']['text']:
        item['content_html'] += render_content(content)

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    if 'rss' in paths:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    if next_data['pageProps'].get('pages'):
        pages = next_data['pageProps']['pages']['pages']
    elif next_data['pageProps'].get('articles'):
        pages = next_data['pageProps']['articles']['pages']

    n = 0
    feed_items = []
    for article in pages:
        article_url = 'https://' + urlsplit(url).netloc + '/' + article['link']
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
    feed['title'] = next_data['pageProps']['siteName']
    if next_data['pageProps'].get('channel'):
        feed['title'] += ' | ' + next_data['pageProps']['channel']['name']
    elif next_data['pageProps'].get('author'):
        feed['title'] += ' | ' + next_data['pageProps']['author']['name']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
