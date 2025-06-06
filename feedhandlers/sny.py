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
        path = '/index'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    path += '.json'

    if 'articles' in paths:
        query = '?slug=' + paths[-1]
    else:
        query = ''

    next_url = '{}://{}/_next/data/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, query)
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

    page_json = next_data['pageProps']
    item = {}
    item['id'] = page_json['uid']
    item['url'] = 'https://' + urlsplit(url).netloc + page_json['url']
    item['title'] = page_json['title']

    dt = datetime.fromisoformat(page_json['publishTimestamp'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['authors'] = [{"name": x['title']} for x in page_json['authors']]
    if len(item['authors']) > 0:
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

    item['tags'] = [x['label'] for x in page_json['tags']]
    if page_json['SEO'].get('keywords'):
        item['tags'] += page_json['SEO']['keywords'].copy()

    if page_json.get('image'):
        item['image'] = page_json['image']['imageUrl']

    if page_json['SEO'].get('description'):
        item['summary'] = page_json['SEO']['description']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] = ''
    if page_json.get('subtitle'):
        item['content_html'] += '<p><em>' + page_json['subtitle'] + '</em></p>'

    if page_json.get('videoData'):
        source = next((it for it in page_json['videoData']['sources'] if it['type'] == 'application/vnd.apple.mpegurl'), None)
        if not source:
            source = utils.closest_dict(page_json['videoData']['sources'], 'width', 960)
            if not source:
                source = page_json['videoData']['sources'][0]
        item['content_html'] += utils.add_video(source['file'], source['type'], utils.clean_url(page_json['videoData']['thumbnail']['url']), page_json['videoData']['title'])
    elif page_json.get('image'):
        item['content_html'] += utils.add_image(page_json['image']['imageUrl'], page_json['image']['title'])

    for block in page_json['htmlBlocks']:
        if block['type'] == 'html':
            if block['html'].startswith('<blockquote'):
                if 'twitter-tweet' in block['html']:
                    m = re.findall('href="([^"]+)', block['html'])
                    item['content_html'] += utils.add_embed(m[-1])
            else:
                item['content_html'] += block['html']
        elif block['type'] == 'image':
            item['content_html'] += utils.add_image(block['image']['imageUrl'], block['image']['title'])
        else:
            logger.warning('unhandled htmlBlock type {} in {}'.format(block['type'], item['url']))

    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
