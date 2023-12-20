import json, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://wbez-rss.streamguys1.com/player/player23111615264653.html
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')

    m = re.search(r'rss:"([^"]+)"', page_html)
    rss_html = utils.get_url_html(m.group(1))

    item = {}
    m = re.search(r'player\d+', url)
    item['id'] = m.group(0)

    el = soup.find('meta', attrs={"property": "og:url"})
    item['url'] = el['content']

    el = soup.find('meta', attrs={"property": "og:title"})
    item['title'] = el['content']

    item['author'] = {}
    m = re.search(r'podcast:"([^"]+)"', page_html)
    item['author']['name'] = m.group(1)
    m = re.search(r'<link>([^<]+)</link>', rss_html)
    item['author']['url'] = m.group(1)

    el = soup.find('meta', attrs={"property": "og:image"})
    item['_image'] = el['content']
    poster = '{}/image?url={}&height=128&overlay=audio'.format(config.server, quote_plus(item['_image']))

    el = soup.find('meta', attrs={"property": "og:description"})
    item['summary'] = el['content']

    el = soup.find('meta', attrs={"property": "twitter:app:url:iphone"})
    item['_audio'] = el['content']
    attachment = {}
    attachment['url'] = item['_audio']
    attachment['mime_type'] = 'audio/mpeg'
    item['attachments'] = []
    item['attachments'].append(attachment)

    display_date = ''
    # Date seems to be part of the audio path, but not sure how universal this is
    m = re.search(r'/(\d+)-[^/]+\.mp3$', item['_audio'])
    if m:
        try:
            dt = dateutil.parser.parse(m.group(1))
            # Extract the timezone from the rss feed
            m = re.search(r'<pubDate>([^<]+)</pubDate>', rss_html)
            if m:
                dt_rss = dateutil.parser.parse(m.group(1))
                dt = dt.replace(tzinfo=dt_rss.tzinfo)
                item['date_published'] = dt.isoformat()
                item['_timestamp'] = dt.timestamp()
                item['_display_date'] = utils.format_display_date(dt)
                display_date = '<div style="font-size:0.8em;">{}</div>'.format(utils.format_display_date(dt, False))
        except:
            pass

    item['content_html'] = '<table><tr><td style="width:128px;"><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div><div><a href="{}">{}</a></div>{}</td></tr></table>'.format(item['_audio'], poster, item['url'], item['title'], item['author']['url'], item['author']['name'], display_date)

    if 'embed' not in args:
        item['content_html'] += '<p>{}</p>'.format(item['summary'])
    return item
