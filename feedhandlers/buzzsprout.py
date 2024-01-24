import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://www.buzzsprout.com/1851795/12031233-how-we-could-stumble-into-ai-catastrophe.js?container_id=buzzsprout-player-12031233&player=small
    clean_url = utils.clean_url(url)
    if clean_url.endswith(('.js')):
        clean_url = clean_url[:-3]
    page_html = utils.get_url_html(clean_url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    soup = BeautifulSoup(page_html, 'lxml')

    split_url = urlsplit(clean_url)
    paths = list(filter(None, split_url.path[1:].split('/')))

    item = {}
    el = soup.find('audio')
    if el:
        item['id'] = el['data-episode-id']
        item['_audio'] = utils.get_redirect_url(el['src'])
        attachment = {}
        attachment['url'] = item['_audio']
        attachment['mime_type'] = el['type']
        item['attachments'] = []
        item['attachments'].append(attachment)
        duration = utils.calc_duration(int(el['data-duration']))

    el = soup.find('meta', attrs={"property": "og:url"})
    if el:
        item['url'] = el['content']
    else:
        item['url'] = clean_url

    el = soup.find(class_='episode__title')
    if el:
        item['title'] = el.get_text().strip()
    else:
        item['title'] = soup.title.get_text().strip()

    el = soup.find(class_='window__info-details')
    if el:
        m = re.search(r'\w+ \d?\d, \d{4}', el.get_text().strip())
        if m:
            dt = datetime.strptime(m.group(0), '%b %d, %Y').replace(tzinfo=timezone.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, False)

    el = soup.find(class_='episode__podcast-title')
    if el:
        item['author'] = {"name": el.get_text().strip()}
    else:
        el = soup.find(class_='podcast-name')
        if el:
            item['author'] = {"name": el.get_text().strip()}
    author_url = '{}:{}/{}'.format(split_url.scheme, split_url.netloc, paths[0])

    el = soup.find('meta', attrs={"property": "og:image"})
    if el:
        item['_image'] = el['content']
    else:
        el = soup.find(class_='artwork')
        if el:
            item['_image'] = el['data-original-url']

    item['content_html'] = '<div style="margin-top:1em;"><a href="{}"><img src="{}/image?url={}&width=128&overlay=audio" style="float:left; margin-right:8px; width:128px;"/></a><div style="overflow:hidden;">'.format(item['_audio'], config.server, quote_plus(item['_image']))
    item['content_html'] += '<a href="{}"><span style="font-size:1.1em; font-weight:bold;">{}</span></a>'.format(item['url'], item['title'])
    item['content_html'] += '<br/><a href="{}">{}</a>'.format(author_url, item['author']['name'])
    item['content_html'] += '<br/><small>{}&nbsp;&bull;&nbsp;{}</small>'.format(item['_display_date'], duration)
    item['content_html'] += '</div><div style="clear:left;">&nbsp;</div></div>'
    return item


def get_feed(url, args, site_json, save_debug=False):
    # TODO: fix rss for podcasts
    #return rss.get_feed(url, args, site_json, save_debug, get_content)
    return None
