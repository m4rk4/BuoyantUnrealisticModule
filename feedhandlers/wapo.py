import json, tldextract
from bs4 import BeautifulSoup

from feedhandlers import fusion, rss
import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + url)
        return None
    next_data = json.loads(el.string)

    if '/video/' in url:
        if next_data['props']['pageProps'].get('videoData'):
            content = next_data['props']['pageProps']['videoData']
        else:
            content = next_data['props']['pageProps']['playlist'][0]
    else:
        content = next_data['props']['pageProps']['globalContent']

    if save_debug:
        utils.write_file(content, './debug/debug.json')

    tld = tldextract.extract(url)
    sites_json = utils.read_json_file('./sites.json')
    site_json = sites_json[tld.domain]

    return fusion.get_item(content, url, args, site_json, save_debug)


def get_feed(url, args, site_json, save_debug=False):
    if '/rss/' in args['url']:
        return rss.get_feed(url, args, site_json, save_debug, get_content)
    else:
        return fusion.get_feed(url, args, site_json, save_debug)