import dateutil.parser
import pytz, re
from bs4 import BeautifulSoup

import config, utils

import logging
logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://player.captivate.fm/episode/466b78ff-8033-410d-9244-a350e3039e28
    m = re.search(r'/episode/([a-f0-9\-]+)', url)
    if not m:
        logger.warning('unhandled url ' + url)
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    item = {}
    soup = BeautifulSoup(page_html, 'html.parser')
    if soup.find('body', class_='not-found'):
        item['content_html'] = '<blockquote><b><a href="{}">{}</a></b></blockquote>'.format(url, soup.title.get_text())
        return item

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
        item['title'] = soup.title.get_text(strip=True)

    el = soup.find(class_='cp-episode-date')
    if el:
        # date = re.sub(r'(\d+)(nd|st|th)', r'\1', el.get_text())
        # dt = datetime.strptime(date, '%d %B %Y')
        tz_loc = pytz.timezone(config.local_tz)
        dt_loc = dateutil.parser.parse(el.get_text(strip=True))
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, date_only=True)

    el = soup.find('meta', attrs={"property": "og:site_name"})
    if el:
        item['author'] = {}
        item['author']['name'] = el['content']
        m = re.search(r'showId:\d\'([a-f0-9\-]+)\'', page_html)
        if m:
            item['author']['url'] = 'https://player.captivate.fm/show/' + m.group(1)

    el = soup.find('img', class_='player-image')
    if el:
        item['image'] = el['src']
    else:
        el = soup.find('meta', attrs={"property": "og:image"})
        if el:
            item['image'] = el['content']

    duration = []
    el = soup.find('audio', class_='player-audio')
    if el:
        item['_audio'] = el.source['src']
        item['_duration'] = utils.calc_duration(float(el['data-duration']))
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

    el = soup.find(class_='player-shownotes')
    if el:
        item['summary'] = el.decode_contents()

    # item['content_html'] = '<table><tr><td style="width:128px;">{}</td><td style="vertical-align:top;"><a href="{}"><b>{}</b></a><br/>by {}<br/><small>{}&nbsp;&bull;&nbsp;{}</small>'.format(poster, item['url'], item['title'], item['author']['name'], item['_display_date'], ', '.join(duration))
    item['content_html'] = utils.format_audio_content(item, logo=config.logo_captivate)
    return item