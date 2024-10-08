import math
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://embed-player.newsoveraudio.com/v4?key=unh80r&id=https://unherd.com/2023/01/how-the-davos-elite-took-back-control/&bgColor=f5f5f5&color=446c76&playColor=446c76
    split_url = urlsplit(url)
    query = parse_qs(split_url.query)
    if not query.get('id') or not query.get('key'):
        logger.warning('unhandled url ' + url)
        return None
    api_url = 'https://api.newsoveraudio.com/v1/player/article?code={}&offPlatform=true'.format(quote_plus(query['id'][0]))
    # print(api_url)
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "authorization": query['key'][0],
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referrer": "https://embed-player.newsoveraudio.com/",
        "sec-ch-ua": "\"Not?A_Brand\";v=\"8\", \"Chromium\";v=\"108\", \"Microsoft Edge\";v=\"108\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36 Edg/108.0.1462.76"
    }
    api_json = utils.get_url_json(api_url, headers=headers)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')
    if api_json['message'] != 'Article found':
        logger.warning('error {} getting api request for ' + url)
        return None
    article_json = api_json['data']['article']

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['shareUrl']
    item['title'] = article_json['name']

    dt = datetime.fromisoformat(article_json['publisherPublicationDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)

    item['author'] = {"name": article_json['publisher']['name']}

    item['_image'] = article_json['image']

    item['_audio'] = article_json['audio']
    attachment = {}
    attachment['url'] = item['_audio']
    attachment['mime_type'] = 'audio/mpeg'
    item['attachments'] = []
    item['attachments'].append(attachment)

    item['content_html'] = utils.add_audio(item['_audio'], item['_image'], item['title'], item['url'], item['author']['name'], '', item['_display_date'], article_json['audioLength'])
    return item