import base64, math, random, re, requests
from datetime import datetime
from urllib.parse import parse_qs, quote, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_clip_content(url, args, site_json, save_debug=False):
    # https://clips.twitch.tv/SpunkyBloodySamosaDAESuppy-PG9fVWXVgXdMJ0St
    # https://clips.twitch.tv/embed?clip=SpunkyBloodySamosaDAESuppy-PG9fVWXVgXdMJ0St&parent=www.example.com
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if 'embed' in paths:
        url_query = parse_qs(split_url.query)
        if url_query.get('clip'):
            clip_slug = url_query['clip'][0]
        else:
            logger.warning('unknown clip slug in ' + url)
            return None
    else:
        if split_url.path.endswith('/'):
            clip_slug = split_url.path[1:-1]
        else:
            clip_slug = split_url.path[1:]

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

    item = {}
    item['id'] = clip_slug
    item['url'] = 'https://clips.twitch.tv/' + clip_slug

    query = {
        "operationName": "ClipsTitle",
        "variables": {
            "slug": clip_slug
        },
        "query": "query ClipsTitle($slug: ID!) {\nclip(slug: $slug) {\nid\ntitle\n}\n}"
    }
    r = session.post('https://gql.twitch.tv/gql', json=query, headers=headers)
    if r.status_code == 200:
        twitch_json = r.json()
        #utils.write_file(twitch_json, './debug/twitch.json')
        item['title'] = twitch_json['data']['clip']['title']

    query = {
        "operationName": "ClipsBroadcasterInfo",
        "variables": {
            "slug": clip_slug
        },
        "query": "query ClipsBroadcasterInfo($slug: ID!) {\nclip(slug: $slug) {\nid\ngame {\nid\nname\ndisplayName\n}\nbroadcaster {\nid\nprofileImageURL(width: 28)\ndisplayName\nlogin\nstream {\nid\n}\n}\n}\n}"
    }
    r = session.post('https://gql.twitch.tv/gql', json=query, headers=headers)
    if r.status_code == 200:
        twitch_json = r.json()
        #utils.write_file(twitch_json, './debug/twitch.json')
        item['author'] = {}
        item['author']['name'] = twitch_json['data']['clip']['broadcaster']['displayName']
        item['author']['url'] = 'https://www.twitch.tv/' + twitch_json['data']['clip']['broadcaster']['login']
        item['author']['avatar'] = twitch_json['data']['clip']['broadcaster']['profileImageURL']

    query = {
        "operationName": "WatchLivePrompt",
        "variables": {
            "slug": clip_slug
        },
        "query": "query WatchLivePrompt($slug: ID!) {\nclip(slug: $slug) {\nid\ndurationSeconds\nbroadcaster {\nid\nlogin\ndisplayName\nstream {\nid\ngame {\ndisplayName\nid\n}\n}\n}\nthumbnailURL(width: 86 height: 45)\n}\n}"
    }
    r = session.post('https://gql.twitch.tv/gql', json=query, headers=headers)
    if r.status_code == 200:
        twitch_json = r.json()
        #utils.write_file(twitch_json, './debug/twitch.json')
        item['_image'] = twitch_json['data']['clip']['thumbnailURL']
        item['content_html'] = utils.add_image(item['_image'])

    query = {
        "operationName": "ClipsDownloadButton",
        "variables": {
            "slug": clip_slug
        },
        "query": 'query ClipsDownloadButton($slug: ID!) {\nclip(slug: $slug) {\nid\nbroadcaster {\nid\n}\ngame {\nid\nname\n}\nplaybackAccessToken(params: {platform: "web" playerType: "clips-download"}) {\nsignature\nvalue\n}\nvideoQualities {\nsourceURL\n}\n}\n}'
    }
    r = session.post('https://gql.twitch.tv/gql', json=query, headers=headers)
    if r.status_code == 200:
        twitch_json = r.json()
        #utils.write_file(twitch_json, './debug/twitch.json')
        item['']
        item['content_html'] = utils.add_image(item['_image'])
        # https://production.assets.clips.twitchcdn.net/OjTnLTxvX1Vl1YF3TCdErQ/AT-cm%7COjTnLTxvX1Vl1YF3TCdErQ.mp4?sig=c984a15674271cfb342a190b7647758740fccf18&token=%7B%22authorization%22%3A%7B%22forbidden%22%3Afalse%2C%22reason%22%3A%22%22%7D%2C%22clip_uri%22%3A%22https%3A%2F%2Fproduction.assets.clips.twitchcdn.net%2FOjTnLTxvX1Vl1YF3TCdErQ%2FAT-cm%257COjTnLTxvX1Vl1YF3TCdErQ.mp4%22%2C%22device_id%22%3A%2241a8658450a45d04%22%2C%22expires%22%3A1688232630%2C%22user_id%22%3A%22%22%2C%22version%22%3A2%7D
    return item


def get_content(url, args, site_json, save_debug=False):
    # https://player.twitch.tv/?video=1639676672
    # https://player.twitch.tv/?channel=reddark_247
    video_id = ''
    channel_id = ''
    split_url = urlsplit(url)
    if split_url.netloc == 'clips.twitch.tv':
        return get_clip_content(url, args, site_json, save_debug)
    elif split_url.netloc == 'player.twitch.tv':
        query = parse_qs(split_url.query)
        if query.get('video'):
            video_id = query['video'][0]
        elif query.get('channel'):
            channel_id = query['channel'][0]
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

    if video_id:
        embed_url = 'https://player.twitch.tv/?autoplay=false&parent=www.google.com&video='.format(video_id)
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
            "query": "fragment NielsenContentMetadataVideo on Video {\nid\ncreatedAt\ntitle\ngame {\nid\ndisplayName\n}\nowner {\nid\nlogin\n}\n}\nquery NielsenContentMetadata(\n$collectionID: ID!\n$login: String!\n$vodID: ID!\n$isCollectionContent: Boolean!\n$isLiveContent: Boolean!\n$isVODContent: Boolean!\n) {\nuser(login: $login) @include(if: $isLiveContent) {\nid\nbroadcastSettings {\nid\ntitle\n}\nstream {\nid\ncreatedAt\ngame {\nid\ndisplayName\n}\n}\n}\nvideo(id: $vodID) @include(if: $isVODContent) {\n...NielsenContentMetadataVideo\n}\ncollection(id: $collectionID) @include(if: $isCollectionContent) {\nid\nitems(first: 1) {\nedges {\nnode {\n...NielsenContentMetadataVideo\n}\n}\n}\n}\n}"
        }
        r = session.post('https://gql.twitch.tv/gql', json=query, headers=headers)
        if r.status_code != 200:
            return None
        twitch_json = r.json()
        #utils.write_file(twitch_json, './debug/twitch.json')
        if not twitch_json:
            return None

        query = {
            "operationName": "VideoMetadata",
            "variables": {
                "channelLogin": twitch_json['data']['video']['owner']['login'],
                "videoID": video_id
            },
            "query": "fragment videoMetadataUser on User {\nid\n}\nfragment videoMetadataVideo on Video {\nid\ntitle\ndescription\npreviewThumbnailURL(height: 60 width: 90)\ncreatedAt\nviewCount\npublishedAt\nlengthSeconds\nbroadcastType\nowner {\nid\nlogin\ndisplayName\n}\ngame {\nid\nboxArtURL\nname\ndisplayName\n}\n}\nquery VideoMetadata($channelLogin: String! $videoID: ID!) {\nuser(login: $channelLogin) {\nid\nprimaryColorHex\nisPartner\nprofileImageURL(width: 70)\nlastBroadcast {\nid\nstartedAt\n}\n}\ncurrentUser {\n...videoMetadataUser\n}\nvideo(id: $videoID) {\n...videoMetadataVideo\n}\n}"
        }
        r = session.post('https://gql.twitch.tv/gql', json=query, headers=headers)
        if r.status_code != 200:
            return None
        twitch_json = r.json()
        #utils.write_file(twitch_json, './debug/twitch.json')

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
            "query": "query VODPreviewOverlay($vodID: ID) {\nvideo(id: $vodID) {\nid\npreviewThumbnailURL(width: 1280 height: 720)\ntitle\n}\n}"
        }
        r = session.post('https://gql.twitch.tv/gql', json=query, headers=headers)
        if r.status_code == 200:
            preview_json = r.json()
            #utils.write_file(twitch_json, './debug/twitch.json')
            if '/_404/' not in preview_json['data']['video']['previewThumbnailURL']:
                item['_image'] = preview_json['data']['video']['previewThumbnailURL']
        if not item.get('_image'):
            item['_image'] = '{}/image?width=1000&height=562'

        caption = '<a href="{}">Watch on Twitch</a>: {}'.format(embed_url, item['title'])

        query = {
            "operationName": "PlaybackAccessToken_Template",
            "variables": {
                "isLive": False,
                "login": "",
                "isVod": True,
                "vodID": video_id,
                "playerType": "site"
            },
            "query": "query PlaybackAccessToken_Template($login: String!, $isLive: Boolean!, $vodID: ID!, $isVod: Boolean!, $playerType: String!) {  streamPlaybackAccessToken(channelName: $login, params: {platform: \"web\", playerBackend: \"mediaplayer\", playerType: $playerType}) @include(if: $isLive) {    value    signature    __typename  }  videoPlaybackAccessToken(id: $vodID, params: {platform: \"web\", playerBackend: \"mediaplayer\", playerType: $playerType}) @include(if: $isVod) {    value    signature    __typename  }}"
        }
        r = session.post('https://gql.twitch.tv/gql', json=query, headers=headers)
        if r.status_code == 200:
            token_json = r.json()
            #utils.write_file(token_json, './debug/twitch.json')
            acbm = base64.b64encode('{}'.encode()).decode('utf-8')
            p = math.floor(9999999 * random.uniform(0, 1))
            # TODO: play_session_id
            vod_url = 'https://usher.ttvnw.net/vod/{}.m3u8?acmb={}&allow_source=true&p={}&play_session_id=&player_backend=mediaplayer&playlist_include_framerate=true&reassignments_supported=true&sig={}&supported_codecs=avc1&token={}&transcode_mode=cbr_v1&cdm=wv&player_version=1.20.0'.format(video_id, quote(acbm), p, token_json['data']['videoPlaybackAccessToken']['signature'], quote(token_json['data']['videoPlaybackAccessToken']['value']))
            # TODO: this doesn't work because of CORS policy. Works with VLC.
            item['content_html'] = utils.add_video(vod_url, 'application/x-mpegURL', item['_image'], caption)
        else:
            item['content_html'] = utils.add_image(item['_image'], caption, link=embed_url)

    elif channel_id:
        embed_url = 'https://player.twitch.tv/?autoplay=false&parent=www.google.com&channel='.format(channel_id)
        query = {
            "operationName": "NielsenContentMetadata",
            "variables": {
                "isCollectionContent": False,
                "isLiveContent": True,
                "isVODContent": False,
                "collectionID": "",
                "login": channel_id,
                "vodID": ""
            },
            "query": "fragment NielsenContentMetadataVideo on Video {\nid\ncreatedAt\ntitle\ngame {\nid\ndisplayName\n}\nowner {\nid\nlogin\n}\n}\nquery NielsenContentMetadata(\n$collectionID: ID!\n$login: String!\n$vodID: ID!\n$isCollectionContent: Boolean!\n$isLiveContent: Boolean!\n$isVODContent: Boolean!\n) {\nuser(login: $login) @include(if: $isLiveContent) {\nid\nbroadcastSettings {\nid\ntitle\n}\nstream {\nid\ncreatedAt\ngame {\nid\ndisplayName\n}\n}\n}\nvideo(id: $vodID) @include(if: $isVODContent) {\n...NielsenContentMetadataVideo\n}\ncollection(id: $collectionID) @include(if: $isCollectionContent) {\nid\nitems(first: 1) {\nedges {\nnode {\n...NielsenContentMetadataVideo\n}\n}\n}\n}\n}"
        }
        r = session.post('https://gql.twitch.tv/gql', json=query, headers=headers)
        if r.status_code != 200:
            return None
        twitch_json = r.json()
        #utils.write_file(twitch_json, './debug/twitch.json')
        if not twitch_json:
            return None

        query = {
            "operationName": "VideoPlayerStreamInfoOverlayChannel",
            "variables": {
                "channel": channel_id
            },
            "query": "query VideoPlayerStreamInfoOverlayChannel($channel: String) {\nuser(login: $channel) {\nid\nprofileURL\ndisplayName\nlogin\nprofileImageURL(width: 150)\nbroadcastSettings {\nid\ntitle\ngame {\nid\ndisplayName\nname\n}\n}\nstream {\nid\nviewersCount\ntags {\nid\nlocalizedName\n}\n}\n}\n}",
        }
        r = session.post('https://gql.twitch.tv/gql', json=query, headers=headers)
        if r.status_code != 200:
            return None
        channel_json = r.json()
        # utils.write_file(twitch_json, './debug/twitch.json')

        item = {}
        item['id'] = channel_json['data']['user']['id']
        item['url'] = 'https://www.twitch.tv/{}'.format(channel_id)
        item['title'] = channel_json['data']['user']['broadcastSettings']['title']

        dt = datetime.fromisoformat(twitch_json['data']['user']['stream']['createdAt'].replace('Z', '+00:00'))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

        item['author'] = {"name": channel_json['data']['user']['displayName']}

        query = {
            "operationName": "VideoPreviewOverlay",
            "variables": {
                "login": channel_id
            },
            "query": "query VideoPreviewOverlay($login: String!) {\nuser(login: $login) {\nid\nstream {\nid\npreviewImageURL(width: 1280 height: 720)\nrestrictionType\n}\n}\n}"

        }
        r = session.post('https://gql.twitch.tv/gql', json=query, headers=headers)
        if r.status_code == 200:
            preview_json = r.json()
            item['_image'] = preview_json['data']['user']['stream']['previewImageURL']
        else:
            item['_image'] = '{}/image?width=1000&height=562'.format(config.server)

        caption = '<a href="{}">Live on Twitch</a>: <a href="{}">{}</a>: {}'.format(embed_url, channel_json['data']['user']['profileURL'], channel_json['data']['user']['displayName'], channel_json['data']['user']['broadcastSettings']['title'])

        query = {
            "operationName": "PlaybackAccessToken",
            "variables": {
                "isLive": True,
                "login": "reddark_247",
                "isVod": False,
                "vodID": "",
                "playerType": "popout"
            },
            "query": "# This query name is VERY IMPORTANT.\n#\n# There is code in twilight-apollo to split links such that\n# this query is NOT batched in an effort to retain snappy TTV.\nquery PlaybackAccessToken($login: String! $isLive: Boolean! $vodID: ID! $isVod: Boolean! $playerType: String!) {\nstreamPlaybackAccessToken(channelName: $login params: {platform: \"web\" playerBackend: \"mediaplayer\" playerType: $playerType}) @include(if: $isLive) {\nvalue\nsignature\n}\nvideoPlaybackAccessToken(id: $vodID params: {platform: \"web\" playerBackend: \"mediaplayer\" playerType: $playerType}) @include(if: $isVod) {\nvalue\nsignature\n}\n}"
        }
        r = session.post('https://gql.twitch.tv/gql', json=query, headers=headers)
        if r.status_code == 200:
            token_json = r.json()
            acbm = base64.b64encode('{}'.encode()).decode('utf-8')
            p = math.floor(9999999 * random.uniform(0, 1))
            # TODO: play_session_id
            vod_url = 'https://usher.ttvnw.net/api/channel/hls/{}.m3u8?acmb={}&allow_source=true&fast_bread=true&p={}&play_session_id=&player_backend=mediaplayer&playlist_include_framerate=true&reassignments_supported=true&sig={}&supported_codecs=avc1&token={}&transcode_mode=cbr_v1&cdm=wv&player_version=1.20.0'.format(channel_id, quote(acbm), p, token_json['data']['streamPlaybackAccessToken']['signature'], quote(token_json['data']['streamPlaybackAccessToken']['value']))
            # TODO: this doesn't work because of CORS policy. Works with VLC.
            item['content_html'] = utils.add_video(vod_url, 'application/x-mpegURL', item['_image'], caption)
        else:
            item['content_html'] = utils.add_image(item['_image'], caption, link=embed_url)
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
