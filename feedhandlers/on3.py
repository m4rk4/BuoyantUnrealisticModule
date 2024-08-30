import json
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlencode, urlsplit

import config, utils
from feedhandlers import wp_posts

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    return 'https://on3static.com/cdn-cgi/image/width={},quality=70/{}'.format(width, img_src)


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
    query = {}
    n = len(paths) - 1
    if 'teams' in paths:
        i = paths.index('teams')
        if i < n:
            query['teams'] = paths[i + 1]
    if 'college' in paths:
        i = paths.index('college')
        if i < n:
            query['college'] = paths[i + 1]
    if 'news' in paths:
        i = paths.index('news')
        if i < n:
            query['slug'] = paths[i + 1]
    if query:
        next_url += '?' + urlencode(query)
    # print(next_url)
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

    item = {}
    item['id'] = article_json['key']
    item['url'] = 'https://www.on3.com' + article_json['fullUrl']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['postDateGMT']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['modifiedDateGMT']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {"name": article_json['author']['name']}

    if article_json.get('tags'):
        item['tags'] = []
        for it in article_json['tags']:
            item['tags'].append(it['name'])

    if article_json.get('head'):
        head_soup = BeautifulSoup(article_json['head'], 'html.parser')
    else:
        head_soup = None

    if article_json.get('featuredImage'):
        item['_image'] = resize_image(article_json['featuredImage']['source'])
    elif head_soup:
        el = head_soup.find('meta', attrs={"property": "og:image"})
        if el:
            item['_image'] = el['content']

    if article_json.get('excerpt'):
        item['summary'] = article_json['excerpt']
    elif head_soup:
        el = head_soup.find('meta', attrs={"name": "description"})
        if el:
            item['summary'] = el['content']
        else:
            el = head_soup.find('meta', attrs={"property": "og:description"})
            if el:
                item['summary'] = el['content']

    if 'embed' in args:
        item['content_html'] = '<div style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(urlsplit(item['url']).netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}" target="_blank">Read</a></p></div></div><div>&nbsp;</div>'.format(config.server, quote_plus(item['url']))
        return item

    item['content_html'] = ''
    if article_json.get('video'):
        item['content_html'] += utils.add_embed('https://cdn.jwplayer.com/v2/media/' + article_json['video'])
    elif article_json.get('featuredImage'):
        item['content_html'] += utils.add_image(resize_image(article_json['featuredImage']['source']), article_json['featuredImage'].get('caption'))

    if article_json.get('isPremium'):
        item['content_html'] += '<p>{}</p>'.format(article_json['body'])
        item['content_html'] += '<h3>Premium content. Subscription is required.</h3>'
    else:
        item['content_html'] += wp_posts.format_content(article_json['body'], item)
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    n = 0
    feed_items = []
    for article in next_data['pageProps']['articles']['list']:
        article_url = 'https://www.on3.com' + article['fullUrl']
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
    if next_data['pageProps'].get('category'):
        feed['title'] = '{} | On3.com'.format(next_data['pageProps']['category']['categoryName'])
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
