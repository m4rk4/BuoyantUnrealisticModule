import feedparser, re, tldextract
import dateutil.parser
from bs4 import BeautifulSoup
from markdown2 import markdown
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if 'a' in paths:
        api_url = '{}/posts/{}'.format(site_json['api_path'], paths[-1])
        alias = ''
    else:
        if site_json.get('collection_alias'):
            alias = site_json['collection_alias']
        elif site_json.get('collection_is_path'):
            alias = paths[0]
        elif site_json.get('collection_is_subdomain'):
            tld = tldextract.extract(url)
            alias = tld.subdomain
        api_url = '{}/collections/{}/posts/{}'.format(site_json['api_path'], alias, paths[-1])
    api_json = utils.get_url_json(api_url,  headers={"Content-Type":"application/json"})
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    item = {}
    item['id']= api_json['data']['id']
    item['url'] = url
    if api_json['data'].get('title'):
        item['title'] = api_json['data']['title']
    else:
        item['title'] = api_json['data']['slug'].replace('-', ' ')

    dt = dateutil.parser.parse(api_json['data']['created'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    dt = dateutil.parser.parse(api_json['data']['updated'])
    item['date_modified'] = dt.isoformat()

    item['author'] = {"name": alias}

    if api_json['data'].get('tags'):
        item['tags'] = api_json['data']['tags'].copy()

    # Add new lines around image so that they are not embedded in a paragraph
    md = re.sub(r'(!\[[^)]+\))', r'\n\1\n', api_json['data']['body'])
    body_soup = BeautifulSoup(markdown(md), 'html.parser')
    if save_debug:
        utils.write_file(str(body_soup), './debug/debug.html')

    for el in body_soup.find_all('blockquote'):
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

    for el in body_soup.find_all('img'):
        new_html = utils.add_image(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        if el.parent and el.parent.name == 'p':
            el.parent.insert_after(new_el)
            el.parent.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()

    item['content_html'] = str(body_soup)
    item['content_html'] = re.sub(r'</blockquote>\s*<blockquote[^>]+>', '', item['content_html'])
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    try:
        d = feedparser.parse(url)
    except:
        logger.warning('Feedparser error ' + url)
        return None
    if save_debug:
        utils.write_file(str(d), './debug/feed.txt')
    n = 0
    feed_items = []
    for entry in d.entries:
        if save_debug:
            logger.debug('getting content for ' + entry['link'])
        item = get_content(entry['guid'], args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                item['url'] = entry['link']
                if entry.get('author'):
                    item['author']['name'] = entry['author']
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    if d.feed.get('title'):
        feed['title'] = d.feed['title']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
