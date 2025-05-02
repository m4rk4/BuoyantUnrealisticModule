import json, pytz, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import datawrapper, rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url, use_proxy=True, use_curl_cffi=True)
    if not page_html:
        return None
    page_soup = BeautifulSoup(page_html, 'lxml')
    next_data = []
    for el in page_soup.find_all('script', string=re.compile(r'^self\.__next_f\.push')):
        i = el.string.find('(') + 1
        j = el.string.rfind(')')
        next_data.append(json.loads(el.string[i:j]))
    if save_debug:
        utils.write_file(next_data, './debug/next.json')

    return None
