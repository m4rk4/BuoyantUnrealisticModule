import json, re, requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote, urlsplit

import config, utils
from feedhandlers import brightcove, rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    # https://player.twitch.tv/?video=1639676672
    split_url = urlsplit(url)
    if split_url.netloc == 'player.twitch.tv':
        query = parse_qs(split_url.query)
        if not query.get('video'):
            logger.warning('unknown video id in ' + url)
            return None
        video_id = query['video'][0]
    else:
        m = re.search(r'/videos/(\d+)', split_url.path)
        if not m:
            logger.warning('unknown video id in ' + url)
            return None
        video_id = m.group(1)

    session = requests.Session()
    r = session.get(url)
    m = re.search(r'cliendId="([^"]+)"', r.text)
    if m:
        client_id = m.group(1)
    else:
        client_id = 'kimne78kx3ncx6brgo4mv6wki5h1ko'
    cookies = session.cookies.get_dict()
    device_id = cookies['unique_id']
    headers = {
        "accept": "*/*",
        "accept-language": "en-US",
        "authorization": "undefined",
        "cache-control": "no-cache",
        "client-id": client_id,
        "content-type": "text/plain; charset=UTF-8",
        "device-id": device_id,
        "pragma": "no-cache",
        "sec-ch-ua": "\"Chromium\";v=\"106\", \"Microsoft Edge\";v=\"106\", \"Not;A=Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site"
    }

    query = {
        "operationName": "NielsenContentMetadata",
        "variables": {
            "isCollectionContent": False,
            "isLiveContent": False,
            "isVODContent": True,
            "collectionID": "",
            "login": "",
            "vodID": video_id
        },
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "2dbf505ee929438369e68e72319d1106bb3c142e295332fac157c90638968586"
            }
        }
    }
    r = session.post('https://gql.twitch.tv/gql', json=query, headers=headers)
    if r.status_code != 200:
        return None
    twitch_json = r.json()
    #utils.write_file(twitch_json, './debug/twitch.json')

    query = {
        "operationName": "VideoMetadata",
        "variables": {
            "channelLogin": twitch_json['data']['video']['owner']['login'],
            "videoID": video_id
        },
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "49b5b8f268cdeb259d75b58dcb0c1a748e3b575003448a2333dc5cdafd49adad"
            }
        }
    }
    r = session.post('https://gql.twitch.tv/gql', json=query, headers=headers)
    if r.status_code != 200:
        return None
    twitch_json = r.json()
    utils.write_file(twitch_json, './debug/twitch.json')

    item = {}
    item['id'] = video_id
    item['url'] = 'https://www.twitch.tv/videos/{}'.format(video_id)
    item['title'] = twitch_json['data']['video']['title']

    dt = datetime.fromisoformat(twitch_json['data']['video']['publishedAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": twitch_json['data']['video']['owner']['displayName']}

    if twitch_json['data']['video'].get('game'):
        item['tags'] = [twitch_json['data']['video']['game']['displayName']]

    if twitch_json['data']['video'].get('description'):
        item['summary'] = twitch_json['data']['video']['description']

    query = {
        "operationName": "VODPreviewOverlay",
        "variables": {
            "vodID": video_id
        },
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "eb2fedc968b3abc7bb04ce35cf7b280d66956ba99a4e459b50e86487851bd335"
            }
        }
    }
    r = session.post('https://gql.twitch.tv/gql', json=query, headers=headers)
    if r.status_code != 200:
        return None
    twitch_json = r.json()
    #utils.write_file(twitch_json, './debug/twitch.json')

    if '/_404/' not in twitch_json['data']['video']['previewThumbnailURL']:
        item['_image'] = twitch_json['data']['video']['previewThumbnailURL']
        poster = item['_image']
    else:
        poster = ''

    query = {
        "operationName": "PlaybackAccessToken_Template",
        "query": "query PlaybackAccessToken_Template($login: String!, $isLive: Boolean!, $vodID: ID!, $isVod: Boolean!, $playerType: String!) {  streamPlaybackAccessToken(channelName: $login, params: {platform: \"web\", playerBackend: \"mediaplayer\", playerType: $playerType}) @include(if: $isLive) {    value    signature    __typename  }  videoPlaybackAccessToken(id: $vodID, params: {platform: \"web\", playerBackend: \"mediaplayer\", playerType: $playerType}) @include(if: $isVod) {    value    signature    __typename  }}",
        "variables": {
            "isLive": False,
            "login": "",
            "isVod": True,
            "vodID": video_id,
            "playerType": "site"
        }
    }
    r = session.post('https://gql.twitch.tv/gql', json=query, headers=headers)
    if r.status_code != 200:
        return None
    twitch_json = r.json()
    #utils.write_file(twitch_json, './debug/twitch.json')

    token = quote(twitch_json['data']['videoPlaybackAccessToken']['value'])
    # TODO: this doesn't work because of CORS policy. Works with VLC.
    # vod_url = 'https://usher.ttvnw.net/vod/{}.m3u8?allow_source=true&p=2265567&play_session_id=682129c6aff9135cc0288386a84eb564&player_backend=mediaplayer&playlist_include_framerate=true&reassignments_supported=true&sig={}&supported_codecs=avc1&token={}&cdm=wv&player_version=1.15.0'.format(video_id, twitch_json['data']['videoPlaybackAccessToken']['signature'], token)
    vod_url = 'https://usher.ttvnw.net/vod/{}.m3u8?allow_source=true&player_backend=mediaplayer&playlist_include_framerate=true&reassignments_supported=true&sig={}&supported_codecs=avc1&token={}&cdm=wv&player_version=1.15.0'.format(video_id, twitch_json['data']['videoPlaybackAccessToken']['signature'], token)
    print(vod_url)

    caption = '{} | <a href="{}">Watch on Twitch</a>'.format(item['title'], item['url'])
    item['content_html'] = utils.add_video(vod_url, 'application/x-mpegURL', poster, caption)
    return item


# Game livestream feed:
# {
#   "operationName": "DirectoryPage_Game",
#   "variables": {
#     "imageWidth": 50,
#     "name": "valorant",
#     "options": {
#       "sort": "RECENT",
#       "recommendationsContext": {
#         "platform": "web"
#       },
#       "requestID": "JIRA-VXP-2397",
#       "freeformTags": null,
#       "tags": []
#     },
#     "sortTypeIsRecency": false,
#     "limit": 30
#   },
#   "extensions": {
#     "persistedQuery": {
#       "version": 1,
#       "sha256Hash": "df4bb6cc45055237bfaf3ead608bbafb79815c7100b6ee126719fac3762ddf8b"
#     }
#   }
# }
#
# Game video feed:
# {
#   "operationName": "DirectoryVideos_Game",
#   "variables": {
#     "gameName": "VALORANT",
#     "videoLimit": 30,
#     "languages": [],
#     "videoSort": "TIME"
#   },
#   "extensions": {
#     "persistedQuery": {
#       "version": 1,
#       "sha256Hash": "c04a45b3adfcfacdff2bf4c4172ca4904870d62d6d19f3d490705c5d0a9e511e"
#     }
#   }
# }
