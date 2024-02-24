import html, json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
from urllib.parse import quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug):
    # https://www.loom.com/embed/8f280344f94c4db588dd1111952c72ee
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', string=re.compile('window\.loomSSRVideo'))
    if not el:
        logger.warning('unable to find loomSSRVideo info in ' + url)
        return None
    i = el.string.find('window.loomSSRVideo =')
    j = el.string[i:].find('{')
    k = el.string.rfind('}') + 1
    video_json = json.loads(el.string[i+j:k])
    if save_debug:
        utils.write_file(video_json, './debug/debug.json')

    # gql_data = [
    #     {
    #         "operationName": "GetVideoSource",
    #         "variables": {
    #             "videoId": "8f280344f94c4db588dd1111952c72ee",
    #             "password": "",
    #             "acceptableMimes": [
    #                 "DASH",
    #                 "M3U8",
    #                 "MP4"
    #             ]
    #         },
    #         "query": "query GetVideoSource($videoId: ID!, $password: String, $acceptableMimes: [CloudfrontVideoAcceptableMime]) {\n  getVideo(id: $videoId, password: $password) {\n    ... on RegularUserVideo {\n      id\n      nullableRawCdnUrl(acceptableMimes: $acceptableMimes, password: $password) {\n        url\n        credentials {\n          Policy\n          Signature\n          KeyPairId\n          Expires\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n"
    #     }
    # ]
    # gql_json = utils.post_url('https://www.loom.com/graphql', json_data=gql_data)
    # if not gql_json:
    #     return None
    # if save_debug:
    #     utils.write_file(gql_json, './debug/debug.json')

    item = {}
    item['id'] = video_json['id']
    item['url'] = 'https://www.loom.com/share/' + video_json['id']
    item['title'] = video_json['name']

    dt = datetime.fromisoformat(video_json['createdAt'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": video_json['owner_full_name']}

    item['_image'] = 'https://cdn.loom.com/' + video_json['defaultThumbnails']['default']
    poster = '{}/image?url={}&width=1000&overlay=video'.format(config.server, quote_plus(item['_image']))

    if video_json['hlsAndDashSources'].get('application/vnd.apple.mpegurl'):
        item['_video'] = video_json['hlsAndDashSources']['application/vnd.apple.mpegurl']['url']
    elif video_json['hlsAndDashSources'].get('application/dash+xml'):
        item['_video'] = video_json['hlsAndDashSources']['application/vnd.apple.mpegurl']['url']

    if video_json.get('description'):
        item['summary'] = video_json['description']

    # m3u8 doesn't work with videojs
    # item['content_html'] = utils.add_video(item['_video'], 'application/x-mpegURL', item['_image'], item['title'])

    # From: https://github.com/Ecno92/loom-dl
    transcode = utils.post_url('https://www.loom.com/api/campaigns/sessions/{}/transcoded-url'.format(item['id']))
    if transcode:
        link = '{}/videojs?src={}&type=video%2Fmp4&poster={}'.format(config.server, quote_plus(transcode['url']), quote_plus(item['_image']))
        item['content_html'] = utils.add_image(poster, item['title'], link=link)
    else:
        link = 'https://www.loom.com/embed/' + item['id']
        item['content_html'] = utils.add_image(poster, item['title'], link=link)

    if 'embed' not in args and '/embed/' not in url and item.get('summary'):
        item['content_html'] += '<p>' + item['summary'] + '</p>'
    return item