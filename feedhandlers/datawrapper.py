import json, re
from bs4 import BeautifulSoup
from datetime import datetime

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    content = utils.get_url_html(url)
    if not content:
        return None

    if save_debug:
        utils.write_file(content, './debug/debug.html')

    m = re.search(r'window\.__DW_SVELTE_PROPS__ = JSON\.parse\((.*?)\);\n', content)
    if not m:
        logger.warning('unable to find __DW_SVELTE_PROPS__ in ' + url)
        soup = BeautifulSoup(content, 'html.parser')
        el = soup.find('meta', attrs={"http-equiv": "REFRESH"})
        if el:
            m = re.search(r'url=([^;]+)', el['content'])
            if m:
                logger.debug('trying ' + m.group(1))
                return get_content(m.group(1), args, save_debug)
        return None

    content_json = json.loads(json.loads(m.group(1)))
    if save_debug:
        utils.write_file(content_json, './debug/debug.json')

    if content_json.get('chart'):
        chart_json = content_json['chart']
    elif content_json.get('data') and content_json['data'].get('chartJSON'):
        chart_json = content_json['data']['chartJSON']
    else:
        logger.warning('unhandled datawrapper content in ' + url)
        return None

    item = {}
    item['id'] = chart_json['publicId']
    item['url'] = url
    item['title'] = BeautifulSoup(chart_json['title'], 'html.parser').get_text()

    dt = datetime.fromisoformat(chart_json['createdAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(chart_json['lastModifiedAt'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if chart_json.get('authorId'):
        item['author']['name'] = chart_json['authorId']
    else:
        item['author']['name'] = chart_json['organizationId']

    item['_image'] = 'https://datawrapper.dwcdn.net/{}/plain-s.png?v=1'.format(item['id'])
    if not utils.url_exists(item['_image']):
        return None

    captions = []
    item['content_html'] = '<h3>{}</h3>'.format(chart_json['title'])
    if chart_json['metadata'].get('describe'):
        if chart_json['metadata']['describe'].get('intro'):
            #item['content_html'] += '<p>{}</p>'.format(chart_json['metadata']['describe']['intro'])
            captions.append(BeautifulSoup(chart_json['metadata']['describe']['intro'], 'html.parser').get_text())
        if chart_json['metadata']['describe'].get('byline'):
            captions.append(chart_json['metadata']['describe']['byline'])
        if chart_json['metadata']['describe'].get('source-name'):
            captions.append(chart_json['metadata']['describe']['source-name'])
    captions.append('<a href="{}">View chart</a>'.format(item['url']))
    item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions), link=url)
    return item


def get_feed(args, save_debug=False):
    return None
