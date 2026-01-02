import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    if save_debug:
        utils.write_file(page_html, './debug/datawrapper.html')

    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('meta', attrs={"http-equiv": "REFRESH"})
    if el:
        m = re.search(r'url=([^;]+)', el['content'])
        if m:
            logger.debug('trying ' + m.group(1))
            return get_content(m.group(1), args, site_json, save_debug)

    chart_json = None
    el = soup.find('script', string=re.compile(r'__DW_SVELTE_PROPS__'))
    if el:
        m = re.search(r'JSON\.parse\((.*?)\);\n', el.string)
        if m:
            svelte_props = json.loads(json.loads(m.group(1)))
            if svelte_props.get('chart'):
                chart_json = svelte_props['chart']
            elif svelte_props.get('data') and svelte_props['data'].get('chartJSON'):
                chart_json = svelte_props['data']['chartJSON']
    else:
        el = soup.find('script', string=re.compile(r'chartJSON:'))
        if el:
            m = re.search(r'chartJSON:\s?(\{.*?\}),\n', el.string)
            if m:
                chart_json = json.loads(m.group(1))

    if not chart_json:
        logger.warning('unable to find chart data in ' + url)
        return None

    if save_debug:
        utils.write_file(chart_json, './debug/datawrapper.json')

    item = {}
    if chart_json.get('publicId'):
        item['id'] = chart_json['publicId']
    elif chart_json.get('id'):
        item['id'] = chart_json['id']

    if chart_json.get('publicUrl'):
        item['url'] = chart_json['publicUrl']
    else:
        item['url'] = url

    item['title'] = BeautifulSoup(chart_json['title'], 'html.parser').get_text()

    dt = datetime.fromisoformat(chart_json['createdAt'].strip('Z') + '+00:00')
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if chart_json.get('lastModifiedAt'):
        dt = datetime.fromisoformat(chart_json['lastModifiedAt'].strip('Z') + '+00:00')
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if chart_json.get('authorId'):
        item['author']['name'] = chart_json['authorId']
    else:
        item['author']['name'] = chart_json['organizationId']

    split_url = urlsplit(item['url'])
    paths = list(filter(None, split_url.path.strip('/').split('/')))
    base_url = 'https://' + split_url.netloc + '/'
    for it in paths:
        base_url += it + '/'
        if it == item['id']:
            break

    item['image'] = base_url + 'full.png'
    if not utils.url_exists(item['image']):
        item['image'] = base_url + 'fallback.png'
        if not utils.url_exists(item['image']):
            item['image'] = base_url + 'plain-s.png?v=1'
            if not utils.url_exists(item['image']):
                el = soup.find('meta', attrs={"property": "og:image"})
                if el:
                    item['image'] = el['content']
                else:
                    el = soup.find('meta', attrs={"property": "twitter:image"})
                    if el:
                        item['image'] = el['content']
                    else:
                        item['image'] = config.server + '/screenshot?viewport=800%2C800&waitfortime=5000&locator=.dw-chart&url=' + quote_plus(item['url'])

    caption = '<a href="' + item['url'] + '" target="_blank">View chart</a>: ' + item['title']
    # if chart_json['metadata'].get('annotate') and chart_json['metadata']['annotate'].get('notes'):
    #     caption += '<br/>' + chart_json['metadata']['annotate']['notes']
    # if chart_json['metadata'].get('describe'):
    #     credits = []
    #     if chart_json['metadata']['describe'].get('source-name'):
    #         credits.append('Source: ' + chart_json['metadata']['describe']['source-name'])
    #     if chart_json['metadata']['describe'].get('byline'):
    #         credits.append('Graphic: ' + chart_json['metadata']['describe']['byline'])
    #     if len(credits) > 0:
    #         caption += '<br/>' + ' | '.join(credits)
    # caption += '<br/><a href="{}" target="_blank">View chart</a>'.format(item['url'])
    item['content_html'] = utils.add_image(item['image'], caption, link=item['url'], overlay=config.chart_button_overlay)

    # captions = []
    # item['content_html'] = '<div style="font-size:1.2em; font-weight:bold;">{}</div>'.format(chart_json['title'])
    # if chart_json['metadata'].get('describe') and chart_json['metadata']['describe'].get('intro'):
    #     item['content_html'] += '<div>{}</div>'.format(chart_json['metadata']['describe']['intro'])

    # if chart_json['metadata'].get('annotate'):
    #     if chart_json['metadata']['annotate'].get('notes'):
    #         captions.append(chart_json['metadata']['annotate']['notes'])
    # if chart_json['metadata'].get('describe'):
    #     if chart_json['metadata']['describe'].get('source-name'):
    #         captions.append('Source: ' + chart_json['metadata']['describe']['source-name'])
    #     if chart_json['metadata']['describe'].get('byline'):
    #         captions.append('Graphic: ' + chart_json['metadata']['describe']['byline'])
    # caption = '<br/>'.join(captions) + '<br/><a href="{}" target="_blank">View chart</a>'.format(item['url'])
    # item['content_html'] += utils.add_image(item['_image'], caption, link=url)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return None
