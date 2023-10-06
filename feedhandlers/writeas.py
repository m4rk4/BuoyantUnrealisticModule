import re
import dateutil.parser
from bs4 import BeautifulSoup
from markdown2 import markdown
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    m = re.search(r'"/api/collections/([^/]+)/posts/([^/]+)/stat"', page_html)
    if not m:
        logger.warning('unable to determine post id in ' + url)
    user_name = m.group(1)
    post_id = m.group(2)

    split_url = urlsplit(url)
    #paths = list(filter(None, split_url.path.split('/')))

    api_url = '{}://{}/api/posts/{}'.format(split_url.scheme, split_url.netloc, post_id)
    api_json = utils.get_url_json(api_url,  headers={"Content-Type":"application/json"})
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    item = {}
    item['id']= api_json['data']['id']
    item['url'] = url
    if api_json['data'].get('title'):
        item['title'] = api_json['data']['title']
    else:
        item['title'] = api_json['data']['slug'].replace('-', ' ')

    dt = dateutil.parser.parse(api_json['data']['created'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    dt = dateutil.parser.parse(api_json['data']['updated'])
    item['date_modified'] = dt.isoformat()

    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('meta', attrs={"name": "author"})
    if el:
        item['author'] = {"name": el['content']}
    else:
        item['author'] = {"name": user_name}

    if api_json['data'].get('tags'):
        item['tags'] = api_json['data']['tags'].copy()

    # Add new lines around image so that they are not embedded in a paragraph
    md = re.sub(r'(!\[[^)]+\))', r'\n\1\n', api_json['data']['body'])
    body_soup = BeautifulSoup(markdown(md), 'html.parser')
    if save_debug:
        utils.write_file(str(body_soup), './debug/debug.html')

    for el in body_soup.find_all('blockquote'):
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

    for el in body_soup.find_all('img'):
        new_html = utils.add_image(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        if el.parent and el.parent.name == 'p':
            el.parent.insert_after(new_el)
            el.parent.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()

    item['content_html'] = str(body_soup)
    item['content_html'] = re.sub(r'</blockquote>\s*<blockquote[^>]+>', '', item['content_html'])
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
