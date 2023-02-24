import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    api_url = '{}://{}/api'.format(split_url.scheme, split_url.netloc)
    if split_url.path.endswith('/'):
        api_url += split_url.path[:-1]
    else:
        api_url += split_url.path
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    item = {}
    item['id'] = api_json['id']
    item['url'] = url
    item['title'] = api_json['title']
    if api_json.get('subtitle'):
        item['title'] += ' ' + api_json['subtitle']

    dt = datetime.fromisoformat(api_json['meta']['article-article:published_time']['content']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(api_json['meta']['article-article:modified_time']['content']).astimezone(timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if api_json['aside'].get('author'):
        item['author']['name'] = api_json['aside']['author']['name']
    if api_json['aside'].get('interviewer'):
        if item.get('author'):
            item['author']['name'] += ' (Interview by {})'.format(api_json['aside']['interviewer']['name'])
        else:
            item['author']['name'] += 'Interview by {}'.format(api_json['aside']['interviewer']['name'])

    item['tags'] = [it.strip() for it in api_json['meta']['meta-keywords']['content'].split(', ')]

    item['_image'] = api_json['meta']['og-og:image']['content']

    item['content_html'] = ''
    if api_json.get('description'):
        item['summary'] = api_json['description']
        item['content_html'] += '<p><em>{}</em></p>'.format(re.sub(r'</?p>', '', api_json['description']))

    for content in api_json['content']:
        if content['type'] == 'editor':
            if content['content']['text'].startswith('<p>'):
                item['content_html'] += content['content']['text']
            else:
                item['content_html'] += '<p>{}</p>'.format(content['content']['text'])

        elif content['type'] == 'image-widget':
            if isinstance(content['content']['image']['url'], str):
                img_src = content['content']['image']['url']
            else:
                img_src = content['content']['image']['url']['src']
            item['content_html'] += utils.add_image(img_src, content['content']['image'].get('text'))

        elif content['type'] == 'video':
            if re.search('vimeo|youtube', content['content']['url']):
                item['content_html'] += utils.add_embed(content['content']['url'])
            else:
                logger.warning('unhandled video {} in {}'.format(content['content']['url'], item['url']))

        elif content['type'] == 'twitter':
            item['content_html'] += utils.add_embed(content['content']['url'])

        elif content['type'] == 'iframe':
            soup = BeautifulSoup(content['content']['value'], 'html.parser')
            item['content_html'] += utils.add_embed(soup.iframe['src'])

        elif content['type'] == 'article-items' or content['type'] == 'pre-sale':
            pass

        else:
            logger.warning('unhandled content type {} in {}'.format(content['type'], item['url']))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table|/li)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    api_url = '{}://{}/api/articles'.format(split_url.scheme, split_url.netloc)
    if len(paths) > 1:
        api_url += '/category/' + paths[-1]

    api_url += '?page=1&sort=new'
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')
    articles = api_json['articles']['items']

    n = 0
    feed_items = []
    feed = utils.init_jsonfeed(args)
    if api_json.get('category'):
        feed['title'] = '80.lv | ' + api_url['category']['name']
    else:
        feed['title'] = '80.lv | Articles'

    for article in articles:
        article_url = '{}://{}/articles/{}'.format(split_url.scheme, split_url.netloc, article['slug'])
        if save_debug:
            logger.debug('getting content from ' + url)
        item = get_content(article_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed['items'] = feed_items.copy()
    return feed
