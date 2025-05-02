import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import wp_posts, rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(next_url, url, site_json):
    logger.debug(next_url)
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
            logger.debug('updating {} buildId'.format(urlsplit(url).netloc))
            site_json['buildId'] = next_data['buildId']
            utils.update_sites(url, site_json)
        return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) != 2:
        logger.warning('unhandled url ' + url)
        return None

    next_url = '{}://{}/_next/data/{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'])
    if paths[0] == 'canada':
        params = '?channel=canada'
        next_url += '/channel/canada'
    else:
        params = '?city=' + paths[0]
        next_url += '/city/' + paths[0]
    params += '&slug' + paths[1]
    next_url += '/' + paths[1] + '.json' + params
    next_data = get_next_data(next_url, url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    article_json = next_data['pageProps']['article']
    item = {}
    item['id'] = article_json['id']
    item['url'] = url
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['created_at'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('updated_at'):
        dt = datetime.fromisoformat(article_json['updated_at'])
        item['date_modified'] = dt.isoformat()

    item['authors'] = [{"name": x['display_name']} for x in article_json['authors']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = []
    if article_json.get('categories'):
        item['tags'] += [x['name'] for x in article_json['categories']]
    if article_json.get('locations'):
        item['tags'] += [x['name'] for x in article_json['locations']]
    if article_json.get('tags'):
        item['tags'] += [x['name'] for x in article_json['tags']]
    if len(item['tags']):
        # Remove duplicates (case-insensitive)
        item['tags'] = list(dict.fromkeys([it.casefold() for it in item['tags']]))
    else:
        del item['tags']

    if article_json.get('meta_description'):
        item['summary'] = article_json['meta_description']

    item['content_html'] = ''
    if article_json.get('featured_image'):
        item['image'] = article_json['featured_image']
        item['content_html'] += utils.add_image(item['image'], article_json.get('featured_image_caption'))

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] += wp_posts.format_content(article_json['content'], item, site_json)

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if 'feed' in paths:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    next_url = '{}://{}/_next/data/{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'])
    if paths[0] == 'canada':
        params = '?channel=canada'
        next_url += '/channel/canada'
    else:
        params = '?city=' + paths[0]
        next_url += '/city/' + paths[0]
    if len(paths) > 1:
        if paths[1] == 'category':
            params += '&category=' + paths[2]
            next_url += '/category/' + paths[2]
        else:
            params += '&channel=' + paths[1]
            next_url += '/channel/' + paths[1]
            if len(paths) > 2:
                if paths[2] == 'category':
                    params += '&category=' + paths[3]
                    next_url += '/category/' + paths[3]
                else:
                    logger.warning('unhandled url ' + url)
    next_url += '.json' + params
    next_data = get_next_data(next_url, url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')

    n = 0
    feed_items = []
    for article in next_data['pageProps']['latestArticles']:
        if article['canada_channel'] == True:
            article_url = 'https://dailyhive.com/canada/'
        else:
            article_url = 'https://dailyhive.com/' + article['locations'][0]['slug'] + '/'
        article_url += article['slug']
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
    if next_data['pageProps'].get('seoTag'):
        feed['title'] = next_data['pageProps']['seoTag']['title']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
