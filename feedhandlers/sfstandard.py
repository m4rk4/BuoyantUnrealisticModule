import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    return utils.clean_url(img_src) + '?w={}&q=75'.format(width)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
        query = ''
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
        query = '?slug=' + '&slug='.join(paths)
    path += '.json'
    next_url = '{}://{}/_next/data/{}/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, query)
    # print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
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
        utils.write_file(next_data, './debug/debug.json')
    article_json = next_data['pageProps']

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['seo']['canonical']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['seo']['opengraphPublishedTime'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['seo']['opengraphModifiedTime'])
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    authors = []
    for it in article_json['authors']:
        authors.append(it['title'])
    if authors:
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if article_json.get('categories'):
        for it in article_json['categories']:
            item['tags'].append(it['title'])
    if article_json.get('tags'):
        for it in article_json['tags']:
            item['tags'].append(it['name'])

    item['content_html'] = ''
    if article_json.get('articleImage'):
        item['_image'] = resize_image(article_json['articleImage']['src'])
        captions = []
        if article_json['articleImage'].get('caption'):
            captions.append(article_json['articleImage']['caption'])
        if article_json['articleImage'].get('credit'):
            captions.append(article_json['articleImage']['credit'])
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    for block in article_json['blocks']:
        if block['name'] == 'core/paragraph':
            if block['attributes']['dropCap']:
                content =  re.sub(r'^(\W*\w)', r'<span style="float:left; font-size:4em; line-height:0.8em;">\1</span>', block['attributes']['content'])
                item['content_html'] += '<p>' + content + '</p>' + '<span style="clear:left;"></span>'
            else:
                item['content_html'] += '<p>' + block['attributes']['content'] + '</p>'
        elif block['name'] == 'core/image':
            captions = []
            if block['attributes'].get('caption'):
                captions.append(block['attributes']['caption'])
            if block['attributes'].get('credit'):
                captions.append(block['attributes']['credit'])
            item['content_html'] += utils.add_image(block['attributes']['url'], ' | '.join(captions))
        elif block['name'] == 'core/video' or block['name'] == 'sf-standard/looping-video':
            captions = []
            if block['attributes'].get('caption'):
                captions.append(block['attributes']['caption'])
            if block['attributes'].get('credit'):
                captions.append(block['attributes']['credit'])
            if block['attributes'].get('poster'):
                poster = block['attributes']['poster']
            else:
                poster = ''
            if '.mp4' in block['attributes']['src']:
                item['content_html'] += utils.add_video(block['attributes']['src'], 'video/mp4', poster, ' | '.join(captions))
            else:
                item['content_html'] += utils.add_video(block['attributes']['src'], 'application/x-mpegURL', poster, ' | '.join(captions))
        elif block['name'] == 'core/embed':
            item['content_html'] += utils.add_embed(block['attributes']['url'])
        elif block['name'] == 'core/heading':
            item['content_html'] += '<h{0}>{1}</h{0}>'.format(block['attributes']['level'], block['attributes']['content'])
        elif block['name'] == 'sf-standard/related-posts-container':
            continue
        else:
            logger.warning('unhandled block {} in {}'.format(block['name'], item['url']))

    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
