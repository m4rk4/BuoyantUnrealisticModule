import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # Only configured for episode embeds
    api_json = None
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "sec-ch-ua": "\" Not;A Brand\";v=\"99\", \"Microsoft Edge\";v=\"103\", \"Chromium\";v=\"103\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }
    split_url = urlsplit(url)
    if split_url.path.startswith('/player-v2'):
        query = parse_qs(split_url.query)
        if not query.get('i'):
            logger.warning('unhandled podbean player url ' + url)
            return None
        api_url = 'https://www.podbean.com/player/' + query['i'][0]
        api_json = utils.get_url_json(api_url, headers=headers)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/podcast.json')
        ep_url = api_json['episodes'][0]['link']
    elif split_url.path.startswith('/e/'):
        ep_url = url
    else:
        logger.warning('unhandled podbean url ' + url)
        return None

    page_html = utils.get_url_html(ep_url)
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', attrs={"type": "application/ld+json"})
    ld_json = json.loads(el.string)
    if save_debug:
        utils.write_file(ld_json, './debug/podcast.json')

    if not api_json:
        el = soup.find('meta', attrs={"name": "twitter:player"})
        m = re.search('i=([^&]+)', el['content'])
        api_url = 'https://www.podbean.com/player/' + m.group(1)
        api_json = utils.get_url_json(api_url, headers=headers)

    item = {}
    item['id'] = api_json['episodes'][0]['id']
    item['url'] = ld_json['url']
    item['title'] = ld_json['name']

    tz_loc = pytz.timezone(config.local_tz)
    dt_loc = datetime.fromisoformat(ld_json['datePublished'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)

    item['author'] = {}
    item['author']['name'] = ld_json['partOfSeries']['name']
    item['author']['url'] = ld_json['partOfSeries']['url']

    el = soup.find('meta', attrs={"name": "og:image"})
    if el:
        item['_image'] = el['content']
    elif api_json:
        item['_image'] = api_json['episodes'][0]['logo']
    if item.get('_image'):
        poster = '{}/image?url={}&width=128&overlay=audio'.format(config.server, quote_plus(item['_image']))
    else:
        poster = '{}/image?height=128&width=128&overlay=audio'.format(config.server)

    attachment = {
        "url": ld_json['associatedMedia']['contentUrl'],
        "mime_type": "audio/mpeg"
    }
    item['attachments'] = []
    item['attachments'].append(attachment)

    item['_duration'] = api_json['episodes'][0]['duration']

    item['summary'] = ld_json['description']

    item['content_html'] = '<table style="width:480px;"><tr><td><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;"><strong><a href="{}">{}</a></strong><br/><small>by <a href="{}">{}</a><br/>{}&nbsp;&bull;&nbsp;{}</small></td></tr></table>'.format(attachment['url'], poster, item['url'], item['title'], api_json['setting']['podcastLink'], api_json['setting']['podcastTitle'], item['_display_date'], item['_duration'])

    if 'embed' not in args:
        item['content_html'] += '<p>{}</p>'.format(item['summary'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
