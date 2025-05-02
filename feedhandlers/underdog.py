import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import dirt

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1280):
    return 'https://underdognetwork.com/_next/image?url={}&w={}&q=75'.format(quote_plus(img_src), width)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
        params = ''
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
        params = ''
        if len(paths) >  1:
            params += '?category=' + paths[1]
        if len(paths) > 2:
            params += '&slug=' + paths[2]
    path += '.json'
    next_url = '{}://{}/_next/data/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, params)
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
    post_json = next_data['pageProps']['post']
    meta_tags = next_data['pageProps']['metaTags']

    item = {}
    item['id'] = post_json['sys']['id']
    item['url'] = url
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['sys']['publishedAt'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)

    item['authors'] = [{"name": x['name']} for x in post_json['authorCollection']['items']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    if meta_tags.get('keywords'):
        item['tags'] = [x.strip() for x in meta_tags['keywords'].split(',')]

    item['content_html'] = ''
    if post_json.get('headerImage'):
        item['image'] = resize_image(post_json['headerImage']['url'])
        # TODO: caption
        item['content_html'] += utils.add_image(item['image'])
    elif meta_tags.get('ogImage'):
        item['image'] = meta_tags['ogImage']

    item['content_html'] += dirt.render_content(post_json['articleBody']['json'], post_json['articleBody']['links'])

    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    n = 0
    feed_items = []
    split_url = urlsplit(url)

    posts = []
    if next_data['pageProps'].get('featuredPosts') and next_data['pageProps']['featuredPosts'].get('posts'):
        posts += next_data['pageProps']['featuredPosts']['posts']
    if next_data['pageProps'].get('nonFeaturedPosts') and next_data['pageProps']['nonFeaturedPosts'].get('posts'):
        posts += next_data['pageProps']['nonFeaturedPosts']['posts']

    for post in posts:
        post_url = 'https://' + split_url.netloc + '/' + post['sport'].lower() + '/' + post['category'].lower() + '/' + post['slug']
        if save_debug:
            logger.debug('getting content from ' + post_url)
        item = get_content(post_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    if next_data['pageProps'].get('meta') and next_data['pageProps']['meta'].get('title'):
        feed['title'] = next_data['pageProps']['meta']['title']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed