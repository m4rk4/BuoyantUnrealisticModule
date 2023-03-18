import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', string=re.compile(r'window\.__INITIAL_STATE__'))
    if not el:
        logger.warning('unable to parse INITIAL_STATE in ' + url)
        return None
    n = el.string.find('{')
    initial_state = json.loads(el.string[n:])
    if save_debug:
        utils.write_file(initial_state, './debug/debug.json')
    article_json = initial_state['article']

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['canonicalUrl']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['publishedAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('updatedAt'):
        dt = datetime.fromisoformat(article_json['updatedAt'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('authors'):
        authors = []
        for it in article_json['authors']:
            authors.append(it['name'])
        if authors:
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author']['name'] = urlsplit(url).netloc

    item['tags'] = []
    for it in article_json['categories']:
        item['tags'].append(it['label'])
    for it in article_json['tags']:
        item['tags'].append(it['label'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''
    if article_json.get('leadText'):
        item['summary'] = re.sub(r'^<p>(.*)</p>$', r'\1', article_json['leadText'])
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    if article_json.get('leadAsset'):
        if article_json['leadAsset']['type'] == 'lead-image':
            item['_image'] = article_json['leadAsset']['imageSource']
            captions = []
            if article_json['leadAsset'].get('imageCredit'):
                if article_json['leadAsset']['imageCredit'].get('caption'):
                    captions.append(re.sub(r'^<p>(.*)</p>$', r'\1', article_json['leadAsset']['imageCredit']['caption']))
                if article_json['leadAsset']['imageCredit'].get('credit'):
                    captions.append(article_json['leadAsset']['imageCredit']['credit'])
            item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    soup = BeautifulSoup(article_json['body'], 'html.parser')
    for el in soup.find_all(class_=['dn-inline-relations-item', 'dn-relation-block', 'dp-plugin-promobox']):
        el.decompose()
    for el in soup.find_all('link', attrs={"source": "drpublish"}):
        el.decompose()
    for el in soup.find_all('p', class_='subhead'):
        el.name = 'h3'
        el.attrs = {}

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
