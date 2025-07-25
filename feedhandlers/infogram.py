import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, unquote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    page_soup = BeautifulSoup(page_html, 'lxml')
    el = page_soup.find('script', string=re.compile(r'window\.infographicData'))
    if not el:
        logger.warning('unable to find window.infographicData in ' + url)
        return None

    i = el.string.find('{')
    j = el.string.rfind('}') + 1
    info_json = json.loads(el.string[i:j])
    if save_debug:
        utils.write_file(info_json, './debug/debug.json')

    item = {}
    item['id'] = info_json['path']
    m = re.search(r'property="og:url" content="([^"]+)"', page_html)
    if m:
        item['url'] = m.group(1)
    else:
        item['url'] = url
    item['title'] = info_json['title']

    dt = datetime.fromisoformat(info_json['updatedAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if info_json.get('embedImageUrl'):
        item['_image'] = info_json['embedImageUrl']
    elif info_json.get('previewImageUrl'):
        item['_image'] = info_json['previewImageUrl']
    elif info_json.get('thumb'):
        item['_image'] = info_json['thumb']

    caption = '<a href="{}">{}</a>'.format(item['url'], item['title'])
    item['content_html'] = utils.add_image(item['_image'], caption, link=item['url'])
    return item
