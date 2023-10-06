import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

import utils
from feedhandlers import wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if 'watch' not in paths:
        logger.warning('unhandled url ' + url)
        return None
    gql_data = {
        "operationName": "Video",
        "variables": {
            "video": paths[-1]
        },
        "query": "query Video($video: String!) {\n  item(id: $video) {\n    ... on Video {\n      id\n      title\n      description\n      duration\n      thumbnailURL\n      url\n      slug\n      shareURL\n      publishedAt\n      disableAds\n      transcript\n      article {\n        ... on ParagraphNode {\n          type: __typename\n          content {\n            text\n            marks {\n              type\n              attrs {\n                href\n                title\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n        }\n        ... on BlockQuoteNode {\n          type: __typename\n          content {\n            type: __typename\n            content {\n              text\n              marks {\n                type\n                attrs {\n                  href\n                  title\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n          }\n        }\n        __typename\n      }\n      tags {\n        text\n        internalTag\n        __typename\n      }\n      show {\n        id\n        title\n        slug\n        description\n        thumbnailURL\n        tags {\n          text\n          internalTag\n          __typename\n        }\n        posterURL\n        __typename\n      }\n      renditions {\n        url\n        type\n        width\n        height\n        __typename\n      }\n      sections {\n        id\n        title\n        slug\n        imageTreatment\n        position\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n"
    }
    gql_json = utils.post_url('https://api.therecount.com/graphql', json_data=gql_data)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')

    if gql_json['data']['item']['__typename'] == 'Video':
        return get_video_content(gql_json['data']['item'], args, site_json, save_debug)

    logger.warning('unhandled content type {} in {}'.format(gql_json['data']['item']['__typename'], url))
    return None


def get_video_content(content_json, args, site_json, save_debug):
    item = {}
    item['id'] = content_json['id']
    item['url'] = content_json['shareURL']
    item['title'] = content_json['title']

    dt = datetime.fromtimestamp(content_json['publishedAt']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if content_json.get('show'):
        item['author'] = {"name": content_json['show']['title']}

    if content_json.get('tags'):
        item['tags'] = []
        for it in content_json['tags']:
            item['tags'].append(it['text'])

    item['_image'] = content_json['thumbnailURL']

    item['content_html'] = utils.add_video(content_json['url'], 'application/x-mpegURL', content_json['thumbnailURL'])

    if content_json.get('transcript'):
        item['content_html'] += '<h3>Transcript:</h3><p>{}</p>'.format(content_json['transcript'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if 'section' in paths:
        gql_data = {
            "operationName": "VideosBySection",
            "variables": {
                "section": paths[-1],
                "offset": 0,
                "limit": 10
            },
            "query":"query VideosBySection($section: String!, $offset: Int, $limit: Int) {\n  items(section: $section, offset: $offset, limit: $limit) {\n    ... on Video {\n      id\n      title\n      description\n      duration\n      thumbnailURL\n      url\n      slug\n      shareURL\n      publishedAt\n      disableAds\n      transcript\n      article {\n        ... on ParagraphNode {\n          type: __typename\n          content {\n            text\n            marks {\n              type\n              attrs {\n                href\n                title\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n        }\n        ... on BlockQuoteNode {\n          type: __typename\n          content {\n            type: __typename\n            content {\n              text\n              marks {\n                type\n                attrs {\n                  href\n                  title\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n          }\n        }\n        __typename\n      }\n      tags {\n        text\n        internalTag\n        __typename\n      }\n      show {\n        id\n        title\n        slug\n        description\n        thumbnailURL\n        tags {\n          text\n          internalTag\n          __typename\n        }\n        posterURL\n        __typename\n      }\n      renditions {\n        url\n        type\n        width\n        height\n        __typename\n      }\n      sections {\n        id\n        title\n        slug\n        imageTreatment\n        position\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n"
        }
        key = 'items'
    elif len(paths) == 0:
        gql_data = {
            "operationName": "LiveVideos",
            "variables": {
                "offset": 0,
                "limit": 10
            },
            "query":"query LiveVideos($offset: Int, $limit: Int) {\n  live(offset: $offset, limit: $limit) {\n    id\n    duration\n    location\n    publishedAt\n    shareURL\n    slug\n    thumbnailURL\n    title\n    url\n    __typename\n  }\n}\n"
        }
        key = 'live'

    gql_json = utils.post_url('https://api.therecount.com/graphql', json_data=gql_data)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/feed.json')

    n = 0
    feed_items = []
    for video in gql_json['data'][key]:
        if save_debug:
            logger.debug('getting content for ' + video['shareURL'])
        item = get_video_content(video, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
