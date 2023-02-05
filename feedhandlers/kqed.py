import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_api_data(data_type, data_id):
    return utils.get_url_json('https://media-api.kqed.org/{}?ids={}'.format(data_type, data_id))


def resize_image(image, width=1024):
    images = []
    for val in image['attributes']['imgSizes'].values():
        images.append(val)
    img = utils.closest_dict(images, 'width', width)
    return img['file']


def add_image(image, width=1024):
    img_src = resize_image(image, width)
    captions = []
    if image['attributes'].get('caption'):
        captions.append(image['attributes']['caption'])
    if image['attributes'].get('credit'):
        captions.append(image['attributes']['credit'])
    return utils.add_image(img_src, ' | '.join(captions))


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    #api_url = 'https://media-api.kqed.org/posts/{}/{}'.format(paths[0], paths[1])
    api_url = 'https://media-api.kqed.org/posts?slug={}'.format(paths[-1])
    post_json = utils.get_url_json(api_url)
    if not post_json:
        return None
    return get_item(post_json['data'][0], post_json['included'], args, site_json, save_debug)


def get_item(post_data, post_included, args, site_json, save_debug=False):
    if save_debug:
        utils.write_file(post_data, './debug/debug.json')

    item = {}
    item['id'] = post_data['id']
    item['url'] = 'https://www.kqed.com/{}/{}'.format(post_data['id'].replace('_', '/'), post_data['attributes']['slug'])
    item['title'] = post_data['attributes']['title']

    tz_loc = pytz.timezone('US/Eastern')
    dt_loc = datetime.fromtimestamp(post_data['attributes']['publishDate'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt_loc = datetime.fromtimestamp(post_data['attributes']['modified'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    authors = []
    for it in post_data['relationships']['authors']:
        author = next((inc for inc in post_included if inc['id'] == it['data']['id']), None)
        if not author:
            api_json = get_api_data(it['data']['type'], it['data']['id'])
            if api_json:
                author = api_json['data']
        if author:
            authors.append(author['attributes']['name'])
    if authors:
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author']['name'] = post_data['attributes']['headTitle']

    item['tags'] = []
    if post_data['relationships'].get('category'):
        for it in post_data['relationships']['category']:
            term = next((inc for inc in post_included if inc['id'] == it['data']['id']), None)
            if not term:
                api_json = get_api_data(it['data']['type'], it['data']['id'])
                if api_json:
                    term = api_json['data']
            if term:
                item['tags'].append(term['attributes']['name'])
    if post_data['relationships'].get('postTag'):
        for it in post_data['relationships']['postTag']:
            term = next((inc for inc in post_included if inc['id'] == it['data']['id']), None)
            if not term:
                api_json = get_api_data(it['data']['type'], it['data']['id'])
                if api_json:
                    term = api_json['data']
            if term:
                item['tags'].append(term['attributes']['name'])
    if not item.get('tags'):
        del item['tags']

    item['summary'] = post_data['attributes']['excerpt']

    item['content_html'] = ''
    if post_data['attributes']['format'] == 'video':
        item['content_html'] += utils.add_embed(post_data['attributes']['videoEmbed'])

    if post_data['relationships'].get('featImg'):
        image = next((inc for inc in post_included if inc['id'] == post_data['relationships']['featImg']['data']['id']), None)
        if not image:
            api_json = get_api_data(it['data']['type'], it['data']['id'])
            if api_json:
                image = api_json['data']
        if image:
            item['_image'] = resize_image(image)
            if post_data['attributes']['format'] != 'video':
                item['content_html'] += add_image(image)

    if post_data['attributes']['format'] == 'audio':
        item['_audio'] = utils.get_redirect_url(post_data['attributes']['audioUrl'])
        attachment = {}
        attachment['url'] = item['_audio']
        attachment['mime_type'] = 'audio/mpeg'
        item['attachments'] = []
        item['attachments'].append(attachment)
        item['content_html'] += '<table><tr><td style="width:48px;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a></td><td><h4><a href="{0}">Listen</a></h4></td></tr></table>'.format(item['_audio'], config.server)

    content_html = re.sub(r'<p>\[ad [^\]]+\]</p>', '', post_data['attributes']['content'])
    content_html = re.sub(r'\[aside [^\]]+\]|\[dl_subscribe\]', '', content_html)
    content_html = re.sub(r'\[(/)?pullquote\]', r'<\1blockquote>', content_html)
    def add_tweet(matchobj):
        return utils.add_embed(matchobj.group(1))
    content_html = re.sub(r'<p>(https://twitter.com/[^/]+/status/\d+)</p>', add_tweet, content_html)

    item['content_html'] += wp_posts.format_content(content_html, item)
    return item


def get_feed(url, args, site_json, save_debug=False):
    if '/feed/' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    posts_json = None
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) > 0:
        page_json = utils.get_url_json('https://media-api.kqed.org/pages/root-site?path=' + paths[0])
        if page_json and page_json.get('data'):
            if save_debug:
                utils.write_file(page_json, './debug/debug.json')
            block = next((it for it in page_json['data'][0]['attributes']['blocks'] if it['blockName'] == 'kqed/post-list'), None)
            if block:
                posts_json = utils.get_url_json('https://media-api.kqed.org/{}&page[size]=10&page[from]=0'.format(block['attrs']['query']))
        else:
            posts_json = utils.get_url_json('https://media-api.kqed.org/posts?tag={}&page[size]=10&page[from]=0'.format(paths[0]))

    if not posts_json:
        return None
    if save_debug:
        utils.write_file(posts_json, './debug/feed.json')

    n = 0
    feed_items = []
    for post_data in posts_json['data']:
        url = 'https://www.kqed.com/{}/{}'.format(post_data['id'].replace('_', '/'), post_data['attributes']['slug'])
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_item(post_data, posts_json['included'], args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    feed['title'] = args['url'].replace('https://', '')
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
