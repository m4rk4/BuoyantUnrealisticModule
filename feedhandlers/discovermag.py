import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    return 'https://{}{}?fm=jpg&fl=progressive&w={}&fit=pad'.format(split_url.netloc, split_url.path, width)


def get_next_json(url):
    sites_json = utils.read_json_file('./sites.json')
    next_url = 'https://www.discovermagazine.com/_next/data/' + sites_json['discovermagazine']['buildId']

    split_url = urlsplit(url)
    if split_url.path:
        next_url += split_url.path + '.json'
    else:
        next_url += '/index.json'

    next_json = utils.get_url_json(next_url, retries=1)
    if not next_json:
        logger.debug('updating discovermagazine.com buildId')
        article_html = utils.get_url_html(url)
        m = re.search(r'"buildId":"([a-f0-9]+)"', article_html)
        if m:
            sites_json['discovermagazine']['buildId'] = m.group(1)
            utils.write_file(sites_json, './sites.json')
            next_json = utils.get_url_json(
                'https://www.discovermagazine.com/_next/data/{}{}.json'.format(m.group(1), split_url.path))
            if not next_json:
                return None
    return next_json


def get_content(url, args, save_debug):
    next_json = get_next_json(url)
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/debug.json')

    article_json = next_json['pageProps']['content']['article']
    item = {}
    item['id'] = article_json['id']
    item['url'] = url
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['meta']['publicationDate']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['meta']['modifiedDate'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    # Check age
    if args.get('age'):
        if not utils.check_age(item, args):
            return None

    authors = []
    for author in article_json['refs']['authors']:
        authors.append(author['name'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    item['tags'].append(article_json['refs']['category']['name'])
    if article_json['refs'].get('tags'):
        for tag in article_json['refs']['tags']:
            item['tags'].append(tag['name'])

    item['_image'] = resize_image(article_json['image']['url'])

    if article_json.get('subtitle'):
        item['summary'] = article_json['subtitle']

    if article_json['image'].get('description'):
        caption = article_json['image']['description']
    else:
        caption = ''
    item['content_html'] = utils.add_image(resize_image(item['_image']), caption)

    def process_content(content):
        nonlocal url
        content_html = ''
        if content['nodeType'] == 'paragraph':
            content_html = '<p>'
            for c in content['content']:
                content_html += process_content(c)
            content_html += '</p>'

        elif content['nodeType'] == 'text':
            content_html = content['value']
            for mark in content['marks']:
                if mark['type'] == 'bold':
                    content_html = '<b>{}</b>'.format(content_html)
                elif mark['type'] == 'italic':
                    content_html = '<i>{}</i>'.format(content_html)
                elif mark['type'] == 'underline':
                    content_html = '<u>{}</u>'.format(content_html)
                else:
                    logger.warning('unhandled mark type {} in {}'.format(mark['type'], url))

        elif content['nodeType'] == 'hyperlink':
            content_html = '<a href="{}">'.format(content['data']['uri'])
            for c in content['content']:
                content_html += process_content(c)
            content_html += '</a>'

        elif content['nodeType'].startswith('heading-'):
            content_html = '<h{}>'.format(content['nodeType'][-1])
            for c in content['content']:
                content_html += process_content(c)
            content_html += '</h{}>'.format(content['nodeType'][-1])

        elif content['nodeType'].endswith('-list'):
            if content['nodeType'].startswith('ordered'):
                tag = 'ol'
            else:
                tag = 'ul'
            content_html = '<{}>'.format(tag)
            for c in content['content']:
                content_html += process_content(c)
            content_html += '</{}>'.format(tag)

        elif content['nodeType'] == 'list-item':
            content_html = '<li>'
            for c in content['content']:
                content_html += process_content(c)
            content_html += '</li>'

        elif content['nodeType'] == 'embedded-asset-block':
            if content['data']['target']['fields'].get('file') and 'image' in \
                    content['data']['target']['fields']['file']['contentType']:
                if content['data']['target']['fields'].get('description'):
                    caption = content['data']['target']['fields']['description']
                else:
                    caption = ''
                content_html = utils.add_image(resize_image(content['data']['target']['fields']['file']['url']),
                                               caption)
            else:
                logger.warning('unhandled embedded-asset-block in ' + url)

        elif content['nodeType'] == 'embedded-entry-block':
            if content['data']['target']['fields'].get('videoUrl'):
                content_html = utils.add_embed(content['data']['target']['fields']['videoUrl'])
            else:
                logger.warning('unhandled embedded-entry-block in ' + url)

        elif content['nodeType'] == 'hr':
            content_html = '<hr/>'

        else:
            logger.warning('unhandled nodeType {} in {}'.format(content['nodeType'], url))

        return content_html

    for c in article_json['body']['content']:
        item['content_html'] += process_content(c)

    return item


def get_feed(args, save_debug):
    # https://www.discovermagazine.com/rss/all
    if '/rss/' in args['url']:
        return rss.get_feed(args, save_debug, get_content)

    # Use category url: https://www.discovermagazine.com/technology
    next_json = get_next_json(args['url'])
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/feed.json')

    feed = utils.init_jsonfeed(args)
    for article in next_json['pageProps']['content']['articles']:
        if not article.get('slug'):
            continue
        article_url = 'https://www.discovermagazine.com/{}/{}'.format(article['refs']['category']['slug'], article['slug'])
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_content(article_url, args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed['items'].append(item)
    return feed
