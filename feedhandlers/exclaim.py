import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index.json'
        query = ''
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
        path += '.json'
        if len(paths) == 3:
            query = '?slug=' + paths[-1]
        elif len(paths) == 2:
            query = '?subCategory=' + paths[-1]
        else:
            query = ''

    next_url = 'https://{}/_next/data/{}{}{}'.format(split_url.netloc, site_json['buildId'], path, query)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url, site_json=site_json)
        if page_html:
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
        utils.write_file(next_data, './debug/next.json')

    article_json = next_data['pageProps']['article']['attributes']

    item = {}
    item['id'] = next_data['pageProps']['article']['id']
    item['url'] = url
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['publishedAt'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['authors'] = [{"name": x['attributes']['name']} for x in article_json['contributors']['data']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = []
    if article_json.get('categories') and article_json['categories'].get('data'):
        item['tags'] += [x['attributes']['title'] for x in article_json['categories']['data']]
    if article_json.get('sub_categories') and article_json['sub_categories'].get('data'):
        item['tags'] += [x['attributes']['title'] for x in article_json['sub_categories']['data']]
    if article_json.get('tags') and article_json['tags'].get('data'):
        item['tags'] += [x['attributes']['title'] for x in article_json['tags']['data']]

    item['content_html'] = ''
    if article_json.get('deck'):
        item['summary'] = article_json['deck']
        item['content_html'] += '<p><em>' + article_json['deck'] + '</em></p>'        

    if article_json.get('photo') and article_json['photo'].get('data'):
        item['image'] = article_json['photo']['data']['attributes']['photo']['data'][0]['attributes']['url']
        if article_json['photo']['data']['attributes'].get('contributor') and article_json['photo']['data']['attributes']['contributor'].get('data'):
            caption = 'Photo: ' + article_json['photo']['data']['attributes']['contributor']['data']['attributes']['name']
        else:
            caption = ''
        item['content_html'] += utils.add_image(item['image'], caption)

    if article_json.get('additionalFields'):
        rating = next((it for it in article_json['additionalFields'] if it.get('Rating')), None)
        if rating:
            num = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"].index(rating['Rating'].lower())
            item['content_html'] += '<div style="display:flex; margin:1em auto; width:36px; height:36px; padding:8px; align-items:center; justify-content:center; aspect-ratio:1 / 1; border-radius:50%; border:4px double #555; color:#555; font:32px Arial, sans-serif;">' + str(num) + '</div>'
            if 'summary' not in item:
                item['summary'] = rating['Rating']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if save_debug:
        utils.write_file(article_json['body'], './debug/debug.html')

    body = BeautifulSoup(article_json['body'], 'html.parser')
    for el in body.find_all('div', class_='raw-html-embed'):
        new_html = ''
        if el.blockquote and 'instagram-media' in el.blockquote['class']:
            new_html = utils.add_embed(el.blockquote['data-instgrm-permalink'])
        elif el.blockquote and 'twitter-tweet' in el.blockquote['class']:
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])
        elif el.iframe:
            new_html = utils.add_embed(el.iframe['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled raw-html-embed in ' + url)

    for el in body.find_all('script'):
        el.decompose()

    item['content_html'] += str(body)
    return item

def get_feed(url, args, site_json, save_debug=False):
    # Feedburner feeds: https://exclaim.ca/feeds
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    n = 0
    feed_items = []
    feed_title = ''
    if len(paths) == 0 or paths[-1] == 'latest' or paths[0] == 'trending':
        if len(paths) == 0 or paths[-1] == 'latest':
            articles = utils.get_url_json('https://exclaim.ca/api/getLatestArticles')
            feed_title = 'Latest Music, Film & Entertainment News | Exclaim!'
        else:
            articles = utils.get_url_json('https://assets.exclaim.ca/raw/upload/trending_slugs_rt_client_v1_1.json')
            feed_title = 'Trending Music, Film & Entertainment News | Exclaim!'
        if articles:
            if save_debug:
                utils.write_file(articles, './debug/feed.json')
            for article in articles:
                article_url = 'https://' + split_url.netloc + '/' + article['category'] + '/article/' + article['slug']
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
    else:
        next_data = get_next_data(url, site_json)
        if not next_data:
            return None
        if save_debug:
            utils.write_file(next_data, './debug/feed.json')
        if next_data['pageProps'].get('metaData') and next_data['pageProps']['metaData'].get('title'):
            feed_title = next_data['pageProps']['metaData']['title']
        for key, val in next_data['pageProps']['__APOLLO_STATE__'].items():
            if key.startswith('ArticleEntity'):
                article_url = 'https://' + split_url.netloc + '/' + val['attributes']['categories']['data'][0]['attributes']['slug'] + '/article/' + val['attributes']['slug']
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

    if len(feed_items) == 0:
        return None

    feed = utils.init_jsonfeed(args)
    if feed_title:
        feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed