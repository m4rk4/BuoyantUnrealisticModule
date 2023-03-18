import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', string=re.compile(r'__DW_SVELTE_PROPS__'))
    if not el:
        logger.warning('unable to find __DW_SVELTE_PROPS__ in ' + url)
        el = soup.find('meta', attrs={"http-equiv": "REFRESH"})
        if el:
            m = re.search(r'url=([^;]+)', el['content'])
            if m:
                logger.debug('trying ' + m.group(1))
                return get_content(m.group(1), args, site_json, save_debug)
        return None

    m = re.search(r'JSON\.parse\((.*?)\);\n', el.string)
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
    if chart_json.get('publicUrl'):
        item['url'] = chart_json['publicUrl']
    else:
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

    el = soup.find('meta', attrs={"property": "og:image"})
    if el:
        item['_image'] = el['content']
    else:
        el = soup.find('meta', attrs={"property": "twitter:image"})
        if el:
            item['_image'] = el['content']
        else:
            item['_image'] = 'https://datawrapper.dwcdn.net/{}/plain-s.png?v=1'.format(item['id'])
    if not utils.url_exists(item['_image']):
        item['_image'] = '{}/screenshot?url={}&width=800&height=800&locator=.dw-chart'.format(config.server, quote_plus(url))

    captions = []
    item['content_html'] = '<div style="font-size:1.2em; font-weight:bold;">{}</div>'.format(chart_json['title'])
    if chart_json['metadata'].get('describe') and chart_json['metadata']['describe'].get('intro'):
        item['content_html'] += '<div>{}</div>'.format(chart_json['metadata']['describe']['intro'])

    if chart_json['metadata'].get('annotate'):
        if chart_json['metadata']['annotate'].get('notes'):
            captions.append(chart_json['metadata']['annotate']['notes'])
    if chart_json['metadata'].get('describe'):
        if chart_json['metadata']['describe'].get('source-name'):
            captions.append('Source: ' + chart_json['metadata']['describe']['source-name'])
        if chart_json['metadata']['describe'].get('byline'):
            captions.append('Graphic: ' + chart_json['metadata']['describe']['byline'])
    caption = '<br/>'.join(captions) + '<br/><a href="{}">View chart</a>'.format(item['url'])
    item['content_html'] += utils.add_image(item['_image'], caption, link=url)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return None
