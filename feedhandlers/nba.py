import math, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    video_id = ''
    split_url = urlsplit(url)
    if split_url.netloc == 'watch.nba.com':
        if split_url.path.startswith('/embed'):
            page_html = utils.get_url_html(url)
            m = re.search(r'seoName:"([^"]+)"', page_html)
            if not m:
                logger.warning('unable to find seoName in ' + url)
                return None
            api_url = 'https://content-api-prod.nba.com/public/1/endeavor/video/{}?ctry=US'.format(m.group(1))
        else:
            logger.warning('unhandled url ' + url)
    elif split_url.path.startswith('/watch'):
        api_url = 'https://content-api-prod.nba.com/public/1{}?ctry=US'.format(split_url.path.replace('/watch/', '/endeavor/'))
    else:
        api_url = 'https://content-api-prod.nba.com/public/1/content{}?ctry=US'.format(split_url.path)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    article_json = api_json['results']
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    if article_json.get('id'):
        item['id'] = article_json['id']
    elif article_json.get('nbaId'):
        item['id'] = article_json['nbaId']

    if article_json.get('permalink'):
        item['url'] = article_json['permalink']
    elif article_json.get('link'):
        item['url'] = article_json['link']

    item['title'] = article_json['title']

    dt = None
    if article_json.get('date'):
        dt = datetime.fromisoformat(article_json['date'].replace('Z', '+00:00'))
    elif article_json.get('releaseDate'):
        dt = datetime.fromisoformat(article_json['releaseDate'].replace('Z', '+00:00'))
    else:
        logger.warning('unknown date in ' + item['url'])
    if dt:
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('modified'):
        dt = datetime.fromisoformat(article_json['modified'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('author'):
        item['author']['name'] = article_json['author']['name']
    else:
        item['author']['name'] = 'NBA.com'

    item['tags'] = []
    for val in article_json['taxonomy'].values():
        if isinstance(val, dict):
            for v in val.values():
                item['tags'].append(v)

    if article_json.get('featuredImage'):
        item['_image'] = article_json['featuredImage']
    elif article_json.get('image'):
        item['_image'] = article_json['image']

    if article_json.get('excerpt'):
        item['summary'] = article_json['excerpt']
    elif article_json.get('description'):
        item['summary'] = article_json['description']

    if article_json['type'] == 'video':
        token_json = utils.get_url_json('https://watch.nba.com/secure/accesstoken?format=json')
        if token_json:
            headers = {
                "accept": "application/json",
                "accept-language": "en-US,en;q=0.9,de;q=0.8",
                "authorization": "Bearer {}".format(token_json['data']['accessToken']),
                "content-type": "application/json",
                "sec-ch-ua": "\" Not A;Brand\";v=\"99\", \"Chromium\";v=\"101\", \"Microsoft Edge\";v=\"101\"",
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": "\"Windows\"",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "cross-site"
            }
            api_url = 'https://nbaapi.neulion.com/api_nba/v1/publishpoint?type=video&id={}&format=json'.format(article_json['program']['id'])
            api_json = utils.get_url_json(api_url, headers=headers)
            if api_json:
                if api_json['streamType'] == 'hls':
                    video_type = 'application/x-mpegURL'
                else:
                    logger.warning('unhandled streamType {}' + api_json['streamType'])
                print(api_json['path'])
                item['content_html'] = utils.add_video(api_json['path'], video_type, item['_image'], item['summary'])
            else:
                logger.warning('unable to get video from ' + api_url)
        else:
            logger.warning('unable to get access token from https://watch.nba.com/secure/accesstoken?format=json')
    else:
        item['content_html'] = wp_posts.format_content(article_json['contentFiltered'], item)
    return item
