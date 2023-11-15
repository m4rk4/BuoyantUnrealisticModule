import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://static.getsnworks.com/ceo/front-end/json-api/
    split_url = urlsplit(url)
    api_url = '{}://{}{}.json'.format(split_url.scheme, split_url.netloc, split_url.path)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')
    return get_item(api_json['article'], url, args, site_json, save_debug)


def get_item(article_json, url, args, site_json, save_debug=False):
    item = {}
    item['id'] = article_json['id']
    item['url'] = url
    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['published_at']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['modified_at']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    if article_json.get('authors'):
        authors = []
        for it in article_json['authors']:
            authors.append(it['name'])
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json.get('tags'):
        item['tags'] = []
        for it in article_json['tags']:
            item['tags'].append(it['name'])

    if article_json.get('abstract'):
        item['summary'] = article_json['abstract']

    item['content_html'] = ''
    if article_json.get('subhead'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['subhead'])

    if article_json.get('dominantMedia'):
        if article_json['dominantMedia']['type'] == 'image':
            item['_image'] = 'https://snworksceo.imgix.net/{}/{}.sized-1000x1000.{}?w=1000'.format(site_json['img_path'], article_json['dominantMedia']['attachment_uuid'], article_json['dominantMedia']['extension'])
            captions = []
            if article_json['dominantMedia'].get('content'):
                captions.append(re.sub(r'^<p>(.*?)</p>$', r'\1', article_json['dominantMedia']['content'].strip()))
            if article_json['dominantMedia'].get('authors'):
                for it in article_json['dominantMedia']['authors']:
                    captions.append(it['name'])
            item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    soup = BeautifulSoup(article_json['content'], 'html.parser')
    for el in soup.find_all(class_='media-embed'):
        new_html = ''
        if el.name == 'img':
            # TODO: where are captions?
            new_html = utils.add_image(el['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled media-embed in ' + item['url'])

    for el in soup.find_all(class_='embed'):
        new_html = ''
        if el.find('blockquote', class_='twitter-tweet'):
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])
        else:
            it = el.find('iframe')
            if it:
                new_html = utils.add_embed(it['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled embed in ' + item['url'])

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if '/section/' not in url and '/author/' not in url and '/staff/' not in url:
        return None
    api_url = '{}://{}{}.json'.format(split_url.scheme, split_url.netloc, split_url.path)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    if isinstance(api_json, list):
        api_json = api_json[0]

    n = 0
    feed_items = []
    for article in api_json['articles']:
        if article.get('published_at'):
            dt = datetime.fromisoformat(article['published_at'])
            article_url = '{}://{}/article/{}/{}/{}'.format(split_url.scheme, split_url.netloc, dt.year, dt.month, article['slug'])
            if save_debug:
                logger.debug('getting content for ' + article_url)
            item = get_item(article, article_url, args, site_json, save_debug)
        elif article.get('published'):
            # Different format??
            dt_loc = datetime.fromtimestamp(int(article['published']))
            tz_loc = pytz.timezone(config.local_tz)
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
            article_url = '{}://{}/article/{}/{}/{}'.format(split_url.scheme, split_url.netloc, dt.year, dt.month, article['slug'])
            if save_debug:
                logger.debug('getting content for ' + article_url)
            item = get_content(article_url, args, site_json, save_debug)
        else:
            logger.warning('unhandled article json content in ' + url)
            continue
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    if '/staff/' in url:
        feed['title'] = api_json['author']['name'] + ' | ' + split_url.netloc
    elif '/section/' in url:
        if api_json['section'].get('title'):
            feed['title'] = api_json['section']['title'] + ' | ' + split_url.netloc
        elif api_json['section'].get('name'):
            feed['title'] = api_json['section']['name'] + ' | ' + split_url.netloc
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed