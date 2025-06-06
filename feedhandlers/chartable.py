import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))

    if split_url.netloc != 'link.chtbl.com':
        logger.warning('unhandled url ' + url)
        return None

    # https://link.chtbl.com/ListenCardLarge
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')
    soup = BeautifulSoup(page_html, 'lxml')

    item = {}
    item['id'] = paths[-1]
    item['url'] = url

    el = soup.find('meta', attrs={"property": "og:title"})
    if el:
        item['title'] = el['content']
    else:
        item['title'] = soup.title.get_text()

    m = re.search(r'"published_at":"([^"]+)";', page_html)
    if m:
        dt = datetime.fromisoformat(m.group(1))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {
        "name": item['title']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    el = soup.find('img', class_='cover-art')
    if el:
        item['image'] = el['src']

    el = soup.find('meta', attrs={"property": "og:description"})
    if el:
        item['summary'] = el['content']
    else:
        el = soup.find('meta', attrs={"name": "description"})
        if el:
            item['summary'] = el['content']

    item['content_html'] = '<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:8px; margin:8px;">'
    poster = config.server + '/image?url=' + quote_plus(item['image']) + '&width=160&overlay=audio'
    item['content_html'] += '<div style="flex:1; min-width:128px; max-width:160px;"><a href="{}/playlist?url={}" target="_blank"><img src="{}" style="width:100%;"/></a></div>'.format(config.server, quote_plus(item['url']), poster)
    item['content_html'] += '<div style="flex:2; min-width:256px;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div></div>'.format(item['url'], item['title'])
    item['content_html'] += '</div>'
    if 'embed' not in args and 'summary' in item:
        item['content_html'] += '<p>' + item['summary'] + '</p>'

    m = re.search(r'host = "([^"]+)";', page_html)
    if m:
        host = m.group(1)
    else:
        host = 'https://chartable.com'

    m = re.search(r'axios\(`(.*?)`\)', page_html)
    if m:
        api_url = m.group(1).replace('${host}', host).replace('${page}', '1')
        feed_json = utils.get_url_json(api_url)
        if feed_json:
            item['_playlist'] = []
            item['content_html'] += '<h3>Episodes:</h3>'
            if 'embed' in args:
                n = 5
            else:
                n = 10
            for episode in feed_json[:n]:
                dt = datetime.fromisoformat(episode['published_at'])
                if 'date_published' not in item:
                    item['date_published'] = dt.isoformat()
                    item['_timestamp'] = dt.timestamp()
                    item['_display_date'] = utils.format_display_date(dt)
                item['content_html'] += utils.add_audio(episode['url'], item['image'], episode['title'], '', '', '', utils.format_display_date(dt, date_only=True), '', show_poster=False)
                item['_playlist'].append({
                    "src": episode['url'],
                    "name": episode['title'],
                    "artist": item['author']['name'],
                    "image": item['image']
                })
    else:
        logger.warning('unknown feed url in ' + url)

    return item


def get_feed(url, args, site_json, save_debug=False):
    return None