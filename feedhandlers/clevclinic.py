import json, re
from bs4 import BeautifulSoup
from curl_cffi import requests
from datetime import datetime
from urllib.parse import unquote_plus, urlsplit

import config, utils
from feedhandlers import semafor

import logging

logger = logging.getLogger(__name__)


def get_next_json(url, save_debug):
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        # "next-router-state-tree": "%5B%22%22%2C%7B%22children%22%3A%5B%5B%22idOrSlug%22%2C%22technology%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D",
        "next-url": "/technology",
        "priority": "u=1, i",
        "rsc": "1",
        "sec-ch-ua": "\"Chromium\";v=\"124\", \"Microsoft Edge\";v=\"124\", \"Not-A.Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }
    r = requests.get(url, headers=headers, impersonate="chrome116", proxies=config.proxies)
    if not r or r.status_code != 200:
        logger.warning('unable to get next data from ' + url)
        return None

    next_data = r.text
    if save_debug:
        utils.write_file(next_data, './debug/next.txt')

    next_json = {}
    x = 0
    m = re.search(r'^\s*([0-9a-f]{1,2}):(.*)', next_data)
    while m:
        key = m.group(1)
        x += len(key) + 1
        val = m.group(2)
        if val.startswith('I'):
            val = val[1:]
            x += 1
        elif val.startswith('HL'):
            val = val[2:]
            x += 2
        elif val.startswith('T'):
            t = re.search(r'T([0-9a-f]+),(.*)', val)
            if t:
                n = int(t.group(1), 16)
                x += len(t.group(1)) + 2
                val = next_data[x:x + n]
                if not val.isascii():
                    i = n
                    n = 0
                    for c in val:
                        n += 1
                        i -= len(c.encode('utf-8'))
                        if i == 0:
                            break
                    val = next_data[x:x + n]
        if val:
            if (val.startswith('{') and val.endswith('}')) or (val.startswith('[') and val.endswith(']')):
                next_json[key] = json.loads(val)
            else:
                next_json[key] = val
            x += len(val)
            if next_data[x:].startswith('\n'):
                x += 1
            m = re.search(r'^\s*([0-9a-f]{1,2}):(.*)', next_data[x:])
        else:
            break
    return next_json


def get_content(url, args, site_json, save_debug=False):
    next_json = get_next_json(url, save_debug)
    if save_debug:
        utils.write_file(next_json, './debug/next.json')

    article_json = None
    content_json = None
    post_json = None
    def iter_list(val):
        nonlocal content_json
        nonlocal post_json
        for v in val:
            if isinstance(v, list) and len(v) > 0:
                if isinstance(v[0], list):
                    iter_list(v)
                elif isinstance(v[0], str) and v[0] == '$' and len(v) == 4 and isinstance(v[3], dict):
                    if v[3].get('data-identity') == 'main-post-content':
                        content_json = v[3]
                    elif v[3].get('post'):
                        post_json = v[3]['post']
                    elif v[3].get('children'):
                        iter_list(v[3]['children'])
            elif isinstance(v, str) and v == '$' and len(val) == 4 and isinstance(val[3], dict):
                if val[3].get('data-identity') == 'main-post-content':
                    content_json = val[3]
                elif val[3].get('post'):
                    post_json = val[3]['post']
                elif val[3].get('children'):
                    iter_list(val[3]['children'])
                break
    for key, val in next_json.items():
        if isinstance(val, list):
            if isinstance(val[0], dict) and val[0].get('@type') and val[0]['@type'] == 'Article':
                article_json = val[0]
            else:
                iter_list(val)
        if article_json and post_json:
            break
    if not article_json:
        logger.warning('unable to find article json in ' + url)
        return None
    if not post_json:
        logger.warning('unable to find post json in ' + url)
        return None
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['_id']
    item['url'] = post_json['canonicalUrl']
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['_createdAt'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('_updatedAt'):
        dt = datetime.fromisoformat(post_json['_updatedAt'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {"name": article_json['author']['name']}

    if post_json.get('category'):
        item['tags'] = []
        for key, val in post_json['category'].items():
            item['tags'].append(val['title'])

    item['content_html'] = ''

    if post_json.get('subtitle'):
        item['content_html'] += '<p><em>' + post_json['subtitle'] + '</em></p>'

    if post_json.get('featuredImage'):
        item['_image'] = post_json['featuredImage']['image']['previewUrl']
        item['content_html'] += utils.add_image(item['_image'])

    item['summary'] = post_json['seo']['description']

    # TODO: check
    def resize_image(image, width=1200):
        return image['previewUrl']

    for block in post_json['content']:
        item['content_html'] += semafor.render_block(block, resize_image)

    item['content_html'] = re.sub(r'</[ou]l><[ou]l>', '', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_json = get_next_json(url, save_debug)
    if save_debug:
        utils.write_file(next_json, './debug/feed.json')

    articles = re.findall(r'"href":\s*"(https://health\.clevelandclinic\.org\/[^"]+)"', json.dumps(next_json['f']))

    # articles = []
    # def iter_list(val):
    #     nonlocal articles
    #     for v in val:
    #         if isinstance(v, list) and len(v) > 0:
    #             if isinstance(v[0], list):
    #                 iter_list(v)
    #             elif isinstance(v[0], str) and v[0] == '$' and len(v) == 4 and isinstance(v[3], dict):
    #                 if v[3].get('data-identity') == 'horizontal-card' or v[3].get('data-identity') == 'vertical-card' or v[3].get('data-identity') == 'headline':
    #                     print(v)
    #                     children = v[3]['children']
    #                     if isinstance(children, list):
    #                         for child in children:
    #                             if isinstance(child, str) and child == '$' and children[1] == 'a':
    #                                 if children[3]['href'].startswith('https') and children[3]['href'] not in articles:
    #                                     articles.append(children[3]['href'])
    #                                 break
    #                             elif isinstance(child, list) and len(child) == 4 and child[0] == '$' and child[1] == 'a':
    #                                 if child[3]['href'].startswith('https') and child[3]['href'] not in articles:
    #                                     articles.append(child[3]['href'])
    #                                 break
    #                 elif v[3].get('children'):
    #                     iter_list(v[3]['children'])
    #         elif isinstance(v, str) and v == '$' and len(val) == 4 and isinstance(val[3], dict):
    #             if val[3].get('data-identity') == 'horizontal-card' or val[3].get('data-identity') == 'vertical-card' or val[3].get('data-identity') == 'headline':
    #                 children = val[3]['children']
    #                 if isinstance(children, list):
    #                     for child in children:
    #                         if isinstance(child, str) and child == '$' and children[1] == 'a':
    #                             if children[3]['href'].startswith('https') and children[3]['href'] not in articles:
    #                                 articles.append(children[3]['href'])
    #                             break
    #                         elif isinstance(child, list) and len(child) == 4 and child[0] == '$' and child[1] == 'a':
    #                             if child[3]['href'].startswith('https') and child[3]['href'] not in articles:
    #                                 articles.append(child[3]['href'])
    #                             break
    #             elif val[3].get('children'):
    #                 iter_list(val[3]['children'])
    #             break
    # for key, val in next_json.items():
    #     if isinstance(val, list):
    #         if isinstance(val[0], dict) and val[0].get('@type') and val[0]['@type'] == 'Article':
    #             article_json = val[0]
    #         else:
    #             iter_list(val)

    if not articles:
        logger.warning('unable to find articles in ' + url)
        return None

    n = 0
    feed_items = []
    for article in articles:
        if save_debug:
            logger.debug('getting content for ' + article)
        item = get_content(article, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    # if next_data['pageProps'].get('self'):
    #     feed['title'] = next_data['pageProps']['self']['name'] + ' | Cowboy State Daily'
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
