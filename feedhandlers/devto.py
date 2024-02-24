import html, json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    # https://media.dev.to/cdn-cgi/image/width=800%2Cheight=%2Cfit=scale-down%2Cgravity=auto%2Cformat=auto/https%3A%2F%2Fdev-to-uploads.s3.amazonaws.com%2Fuploads%2Farticles%2Fi9xwbg4mlq9fh6nj72te.png
    if 'https://media.dev.to/cdn-cgi/' in img_src:
        m = re.search(r'/https.*', img_src)
        if m:
            return 'https://media.dev.to/cdn-cgi/image/width={}%2Cheight=%2Cfit=scale-down%2Cgravity=auto%2Cformat=auto{}'.format(width, m.group(0))
    return img_src


def get_content(url, args, site_json, save_debug):
    # https://developers.forem.com/api
    headers = config.default_headers.copy()
    headers['accept'] = 'application/vnd.forem.api-v1+json'
    split_url = urlsplit(url)
    api_url = site_json['api_path'] + '/articles' + split_url.path
    article_json = utils.get_url_json(api_url, headers=headers)
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['canonical_url']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['published_at'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('edited_at'):
        dt = datetime.fromisoformat(article_json['edited_at'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {"name": article_json['user']['username']}

    if article_json.get('tags'):
        item['tags'] = article_json['tags'].copy()

    if article_json.get('description'):
        item['summary'] = article_json['description']

    item['content_html'] = ''
    if article_json.get('cover_image'):
        item['_image'] = article_json['cover_image']
        item['content_html'] += utils.add_image(item['_image'])

    body = BeautifulSoup(article_json['body_html'], 'html.parser')
    for el in body.find_all(class_='article-body-image-wrapper'):
        it = el.find('img')
        if it:
            img_src = resize_image(it['src'])
            if el.name == 'a':
                link = el['href']
            else:
                link = ''
            # TODO: caption
            new_html = utils.add_image(img_src, link=link)
            new_el = BeautifulSoup(new_html, 'html.parser')
            if el.parent and el.parent.name == 'p':
                el.parent.insert_after(new_el)
                el.parent.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()
        else:
            logger.warning('unhandled article-body-image-wrapper in ' + item['url'])

    for el in body.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        if el.parent and el.parent.name == 'p':
            el.parent.insert_after(new_el)
            el.parent.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()

    for el in body.find_all('div', class_='highlight'):
        it = el.find(class_='highlight__panel')
        if it:
            it.decompose()
        it = el.find('pre')
        if it:
            it.attrs = {}
            it['style'] = 'padding:0.5em; white-space:pre; overflow-x:auto; background:#F2F2F2;'
            # TODO: remove code highlight classes
            # el.unwrap()

    for el in body.find_all('blockquote', class_=False, recursive=False):
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

    item['content_html'] += str(body)
    return item


def get_feed(url, args, site_json, save_debug=False):
    if '/feed' in url:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) == 0:
        feed_url = 'https://dev.to/feed'
        return rss.get_feed(feed_url, args, site_json, save_debug, get_content)
    elif len(paths) == 1:
        feed_url = 'https://dev.to/feed/' + paths[0]
        return rss.get_feed(feed_url, args, site_json, save_debug, get_content)
    elif '/t/' in url:
        feed_url = 'https://dev.to/search/feed_content?per_page=10&page=0&tag={0}&sort_by=published_at&sort_direction=desc&tag_names%5B%5D={0}&approved=&class_name=Article'.format(paths[1])
        feed_content = utils.get_url_json(feed_url)
        if save_debug:
            utils.write_file(feed_content, './debug/feed.json')
        n = 0
        feed_items = []
        for article in feed_content['result']:
            article_url = 'https://dev.to' + article['path']
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
        feed['title'] = '{} | dev.to'.format(paths[1])
        feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
        return feed

    logger.warning('unhandled feed url ' + url)
    return None
