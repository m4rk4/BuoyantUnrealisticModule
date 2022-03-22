import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, unquote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    m = re.search(r'<script>window\.infographicData=({.*?});</script>', page_html)
    if not m:
        return None
    info_json = json.loads(m.group(1))
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

    item['_image'] = info_json['embedImageUrl']

    caption = '<a href="{}">{}</a>'.format(item['url'], item['title'])
    item['content_html'] = utils.add_image(item['_image'], caption, link=item['url'])
    return item
