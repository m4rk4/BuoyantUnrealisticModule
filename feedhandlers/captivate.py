import math, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus

import config, utils

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
    # https://player.captivate.fm/episode/466b78ff-8033-410d-9244-a350e3039e28
    m = re.search(r'/episode/([a-f0-9\-]+)', url)
    if not m:
        logger.warning('unhandled url ' + url)
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    soup = BeautifulSoup(page_html, 'html.parser')

    item = {}
    item['id'] = m.group(1)

    el = soup.find('meta', attrs={"property": "og:url"})
    if el:
        item['url'] = el['content']
    else:
        item['url'] = url

    el = soup.find('meta', attrs={"property": "og:title"})
    if el:
        item['title'] = el['content']
    else:
        item['title'] = soup.title.get_text()

    el = soup.find(class_='cp-episode-date')
    if el:
        date = re.sub(r'(\d+)(nd|st|th)', r'\1', el.get_text())
        dt = datetime.strptime(date, '%d %B %Y')
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, False)

    el = soup.find('meta', attrs={"property": "og:site_name"})
    if el:
        item['author'] = {}
        item['author']['name'] = el['content']
        m = re.search(r'showId:\d\'([a-f0-9\-]+)\'', page_html)
        if m:
            item['author']['url'] = 'https://player.captivate.fm/show/' + m.group(1)

    el = soup.find('img', class_='player-image')
    if el:
        item['_image'] = el['src']
    else:
        el = soup.find('meta', attrs={"property": "og:image"})
        if el:
            item['_image'] = el['content']
    if item.get('_image'):
        poster = '{}/image?url={}&height=128'.format(config.server, quote_plus(item['_image']))
    else:
        poster = '{}/image?height=128&width=128'.format(config.server)

    duration = []
    el = soup.find('audio', class_='player-audio')
    if el:
        item['_audio'] = el.source['src']
        t = math.floor(float(el['data-duration']) / 3600)
        if t >= 1:
            duration.append('{} hr'.format(t))
        t = math.ceil((float(el['data-duration']) - 3600 * t) / 60)
        if t > 0:
            duration.append('{} min.'.format(t))
    else:
        el = soup.find('meta', attrs={"name": "twitter:player:stream"})
        if el:
            item['_audio'] = el['content']
    if item.get('_audio'):
        attachment = {}
        attachment['url'] = item['_audio']
        attachment['mime_type'] = 'audio/mpeg'
        item['attachments'] = []
        item['attachments'].append(attachment)
        poster = '<a href="{}"><img src="{}&overlay=audio"/></a>'.format(item['_audio'], poster)
    else:
        poster = '<img src="{}"/>'.format(poster)

    el = soup.find(class_='player-shownotes')
    if el:
        item['summary'] = el.decode_contents()

    item['content_html'] = '<table><tr><td style="width:128px;">{}</td><td style="vertical-align:top;"><a href="{}"><b>{}</b></a><br/>by {}<br/><small>{}&nbsp;&bull;&nbsp;{}</small>'.format(poster, item['url'], item['title'], item['author']['name'], item['_display_date'], ', '.join(duration))
    return item