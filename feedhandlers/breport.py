import json, html, math, re, uuid
import curl_cffi
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    if split_url.netloc == 'img.bleacherreport.net':
        m = re.search(r'w=(\d+)', split_url.query)
        if m:
            w = int(m.group(1))
        m = re.search(r'h=(\d+)', split_url.query)
        if m:
            h = int(m.group(1))
        height = math.floor(h * width / w)
        img_src = 'https://img.bleacherreport.net{}?w={}&h={}&q=75'.format(split_url.path, width, height)
    elif split_url.netloc == 'media.bleacherreport.com':
        # https://cloudinary.com/documentation/image_transformations
        paths = split_url.path.split('/')
        img_src = 'https://media.bleacherreport.com/image/upload/w_{},c_fill/{}/{}'.format(width, paths[-2], paths[-1])
    return img_src


def format_element(element):
    content_html = ''
    if element.get('contentType'):
        if element['contentType'] == 'paragraph':
            content_html += html.unescape(element['content']['html'])

        elif element['contentType'] == 'image':
            captions = []
            if element['content']['image'].get('caption'):
                captions.append(element['content']['image']['caption'])
            if element['content']['image'].get('accreditation'):
                captions.append(element['content']['image']['accreditation'])
            content_html += utils.add_image(element['content']['image']['url'], ' | '.join(captions))

        elif element['contentType'] == 'youtube' or element['contentType'] == 'twitter':
            content_html += utils.add_embed(element['content']['url'])

        elif element['contentType'] == 'iframe':
            if 'statmilk.bleacherreport.com' in element['content']['url']:
                caption = '<a href="{}" target="_blank">View content</a>'
                content_html += utils.add_image(config.server + '/screenshot?cropbbox=1&url=' + quote_plus(element['content']['url']), caption, link=element['content']['url'])
            else:
                content_html += utils.add_embed(element['content']['url'])

        elif element['contentType'] == 'list':
            content_html += element['content']['html']

        elif element['contentType'] == 'spacer':
            content_html += '<div style="height:2em;"></div>'

        elif element['contentType'] == 'blockquote':
            content_html += utils.add_blockquote(element['content']['html'])

        elif element['contentType'] == 'quote_indent':
            content_html += utils.add_pullquote(element['content']['html'])

        elif element['contentType'] == 'slide':
            content_html += '<h3>{}</h3>'.format(element['title'])
            for slide in element['elements']:
                content_html += format_element(slide)

        elif element['contentType'] == 'ul' or element['contentType'] == 'ol':
            content_html += '<{}>'.format(element['contentType'])
            for it in element['content']['items']:
                content_html += '<li>{}</li>'.format(it)
            content_html += '</{}>'.format(element['contentType'])

        elif element['contentType'] == 'hr':
            content_html += '<hr/>'

        elif element['contentType'] == 'hr_transparent':
            content_html += '<hr style="margin:20px auto; height:1em; color:hsla(0,0%,100%,0); opacity:0;" />'

        elif element['contentType'] == 'ad':
            pass

        else:
            logger.warning('unhandled element with contentType ' + element['contentType'])

    elif element.get('type'):
        if element['type'] == 'media slot':
            pass
        else:
            logger.warning('unhandled element with type ' + element['type'])

    else:
        logger.warning('unhandled element with no contentType or type')

    return content_html


def get_user_post(url, args, site_json, save_debug=False):
    post_html = utils.get_url_html(url)
    if not post_html:
        return None
    m = re.search(r'<!--\s+window\.INITIAL_STORE_STATE = ({.+?});\s+-->', post_html)
    if not m:
        logger.warning('unable to parse INITIAL_STORE_STATE data from ' + url)
        return None
    state_json = json.loads(m.group(1))
    if save_debug:
        utils.write_file(state_json, './debug/debug.json')

    item = {}
    item['id'] = state_json['page']['id']
    item['url'] = state_json['user_post']['shareUrl']
    item['title'] = state_json['user_post']['content']['description']
    if len(item['title']) > 50:
        m = re.search(r'^([\w\W\d\D\s]{50}[^\s]*)', item['title'], flags=re.S | re.U)
        item['title'] = m.group(1) + '...'

    dt = datetime.fromisoformat(state_json['user_post']['inserted_at'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": state_json['user_post']['authorInfo']['username']}

    item['summary'] = state_json['user_post']['content']['description']

    if state_json['user_post']['authorInfo'].get('photo_url'):
        avatar = '{}/image?url={}&height=48&mask=ellipse'.format(config.server, quote_plus(state_json['user_post']['authorInfo']['photo_url']))
    else:
        avatar = '{}/image?width=48&height=48&mask=ellipse'.format(config.server)

    item['content_html'] = '<div style="width:488px; padding:8px 0 8px 8px; border:1px solid black; border-radius:10px; font-family:Roboto,Helvetica,Arial,sans-serif;"><div><img style="float:left; margin-right:8px;" src="{0}"/><span style="line-height:48px; vertical-align:middle;"><b>{1}</b></span></div><br/><div style="clear:left;"></div>'.format(avatar, item['author']['name'])

    if state_json['user_post'].get('media'):
        for media in state_json['user_post']['media']:
            item['content_html'] += media

    item['content_html'] += '<p>{}</p><small>{}</p></div>'.format(item['summary'], item['_display_date'])
    return item


def get_track_content(track, args, site_json, save_debug=False):
    if save_debug:
        utils.write_file(track, './debug/debug.json')

    url = track['content']['metadata']['share_url']
    if url.startswith('https://bleacherreport.com/articles/'):
        return get_content(url, args, site_json, save_debug)

    if '/user_post/' in url:
        return get_user_post(url, args, site_json, save_debug)

    if track['content_type'] == 'poll' or track['content_type'] == 'external_article' or track['content_type'] == 'deeplink' or track['content_type'] == 'bet_track':
        logger.warning('skipping track content_type {} in {}'.format(track['content_type'], url))
        return None

    item = {}

    if track['content']['metadata'].get('stub_id'):
        item['id'] = track['content']['metadata']['stub_id']
    else:
        item['id'] = track['id']

    item['url'] = url

    if track['content']['metadata'].get('title'):
        item['title'] = track['content']['metadata']['title']
    elif track['content']['commentary'].get('title'):
        item['title'] = track['content']['commentary']['title']
    elif track['content']['metadata'].get('caption'):
        item['title'] = track['content']['metadata']['caption']
        if len(item['title']) > 50:
            m = re.search(r'^([\w\W\d\D\s]{50}[^\s]*)', item['title'], flags=re.S|re.U)
            item['title'] = m.group(1) + '...'

    dt = datetime.fromisoformat(track['created_at'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(track['updated_at'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if track['content']['metadata'].get('author_name'):
        item['author']['name'] = track['content']['metadata']['author_name']
    elif track.get('performed_by'):
        item['author']['name'] = track['performed_by']
    elif track['content']['metadata'].get('provider_name'):
        item['author']['name'] = track['content']['metadata']['provider_name']

    if track['content']['metadata'].get('tags'):
        item['tags'] = track['content']['metadata']['tags'].copy()
    elif track.get('tag'):
        item['tags'] = []
        item['tags'].append(track['tag']['display_name'])

    if track['content']['metadata'].get('thumbnail_url'):
        item['_image'] = resize_image(track['content']['metadata']['thumbnail_url'])

    if track['content']['metadata'].get('description'):
        item['summary'] = track['content']['metadata']['description']
    elif track['content'].get('commentary'):
        item['summary'] = track['content']['commentary']['description']

    if track['content_type'] == 'highlight':
        item['_video'] = track['content']['metadata']['mp4_url']
        item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['_image'], track['content']['title'])
        if item.get('summary'):
            item['content_html'] += '<p>{}</p>'.format(item['summary'])

    elif track['content_type'] == 'tweet':
        item['content_html'] = utils.add_embed(track['url'])
        if item.get('summary'):
            item['content_html'] += '<p>{}</p>'.format(item['summary'])

    return item


def get_bolt_headers():
    device_id = str(uuid.uuid4())

    # Static value in https://bleacherreport.com/_next/static/chunks/16388-a7d676238e429877.js
    client_id = 'a63207fb-54ef-4b04-9de2-09754c483096'

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"135\", \"Not-A.Brand\";v=\"8\", \"Chromium\";v=\"135\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "x-device-info": "br/10.3.2 (desktop/desktop; Windows/10; {}/{})".format(device_id, client_id),
        "x-disco-client": "WEB:10:br:10.3.2",
        "x-disco-params": "realm=bolt,bid=br,features=ar"
    }

    token_json = utils.get_url_json('https://default.any-any.prd.api.bleacherreport.com/token?realm=bolt', headers=headers)
    if not token_json:
        logger.warning('unable to get authorization token')
        return headers

    headers['authorization'] = 'Bearer ' + token_json['data']['attributes']['token']

    # This is GSP_FEDERATED_TOKEN in the page source
    headers['x-fedapi-auth'] = 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJodHRwczovL2FwaS9ncmFwaHFsIjp7InJvbGVzIjpbImRpcmVjdG9yIl0sInBlcm1pc3Npb25zIjpbInJlYWQ6YW55X3VzZXIiLCJyZWFkOm93bl91c2VyIl19LCJpYXQiOjE3MzQwOTEyMDAsImV4cCI6MTc2NTYyNzIwMCwic3ViIjoiMTIzNDUifQ.Obp6AWPDfVkI6PkN5Dc9n31fwGkmtQTBEGySkf5Cz2s'
    return headers


def get_video_v2(content_id, headers={}):
    if not headers:
        headers = get_bolt_headers()

    m = re.search(r'\s([0-9a-f\-]+)/', headers['x-device-info'])
    device_id = m.group(1)

    query = {
        "appBundle": "10.3.2.5",
        "advertisingInfo": {
            "debug": {},
            "device": {},
            "googlePALNonce": "",
            "server": {
                "deviceId": "",
                "fwSyncUserId": "",
                "iabTCFString": "",
                "iabUSPrivacy": "1---",
                "isLimitedAdTracking": 0,
                "nielsenAppId": "",
                "prismUkid": str(uuid.uuid4())
            },
            "ssaiProvider": {
                "version": "2.2.0"
            }
        },
        "consumptionType": "streaming",
        "deviceInfo": {
            "deviceId": device_id,
            "browser": {
                "name": "Edge",
                "version": "135.0.0.0"
            },
            "make": "desktop",
            "model": "desktop",
            "os": {
                "name": "Windows",
                "version": "10"
            },
            "platform": "WEB",
            "deviceType": "web",
            "player": {
                "sdk": {
                    "name": "bolt_web",
                    "version": "10.3.2"
                },
                "mediaEngine": {
                    "name": "GLUON_BROWSER",
                    "version": "5.2.1"
                },
                "playerView": {
                    "height": 1080,
                    "width": 1920
                }
            }
        },
        "editId": content_id,
        "capabilities": {
            "manifests": {
                "formats": {
                    "dash": {}
                }
            },
            "codecs": {
                "audio": {
                    "decoders": [
                        {
                            "codec": "aac",
                            "profiles": [
                                "lc",
                                "hev",
                                "hev2"
                            ]
                        },
                        {
                            "codec": "ac3",
                            "profiles": []
                        },
                        {
                            "codec": "eac3",
                            "profiles": [
                                "atmos"
                            ]
                        }
                    ]
                },
                "video": {
                    "decoders": [
                        {
                            "codec": "h264",
                            "profiles": [
                                "high",
                                "main",
                                "baseline"
                            ],
                            "maxLevel": "5.2",
                            "levelConstraints": {
                            "width": {
                                "min": 0,
                                "max": 1920
                            },
                            "height": {
                                "min": 0,
                                "max": 1080
                            },
                            "framerate": {
                                "min": 0,
                                "max": 60
                            }
                            }
                        }
                    ],
                    "hdrFormats": []
                }
            },
            "contentProtection": {
                "contentDecryptionModules": [
                    {
                        "drmKeySystem": "clearkey"
                    },
                    {
                    "drmKeySystem": "playready",
                    "maxSecurityLevel": "sl2000"
                    },
                    {
                    "drmKeySystem": "widevine",
                    "maxSecurityLevel": "l3"
                    }
                ]
            },
            "devicePlatform": {
                "memory": {
                    "allocatedMemory": 0,
                    "freeAvailableMemory": 1.7976931348623157e+308
                },
                "network": {
                    "capabilities": {
                        "protocols": {
                            "http": {
                                "byteRangeRequests": True
                            }
                        }
                    },
                    "lastKnownStatus": {
                        "networkTransportType": "unknown"
                    }
                },
                "videoSink": {
                    "capabilities": {
                        "colorGamuts": [
                            "standard"
                        ],
                        "hdrFormats": []
                    },
                    "lastKnownStatus": {
                        "height": 1080,
                        "width": 1920
                    }
                }
            }
        },
        "gdpr": False,
        "firstPlay": False,
        "playbackSessionId": str(uuid.uuid4()),
        "applicationSessionId": str(uuid.uuid4()),
        "userPreferences": {
            "videoQuality": "best",
            "uiLanguage": "en-US"
        },
        "features": [
            "mlp"
        ]
    }

    # headers['accept'] = 'application/json, text/plain, */*'
    headers['sec-fetch-site'] = 'same-site'

    video_json = utils.post_url('https://default.any-any.prd.api.bleacherreport.com/any/playback/v1/playbackInfo', json_data=query, headers=headers)
    return video_json, headers


def get_article(display_id, tenant, headers={}):
    if not headers:
        headers = get_bolt_headers()

    # headers['accept'] = '*/*'
    headers['sec-fetch-site'] = 'cross-site'

    variables = {
        "displayId": int(display_id),
        "tenant": tenant
    }
    # Query hashes are in https://bleacherreport.com/_next/static/chunks/14141-ee0d12dd47b557fc.js
    extensions = {
        "persistedQuery": {
            "version": 1,
            "sha256Hash": "59529051c27e973439e221ca118f8c1427f210a75e7bcb7dcfa89633fc9edd78"
        }
    }
    gql_url = 'https://fed-api.sportsplatform.io/graphql?operationName=GetArticle&variables=' + quote_plus(json.dumps(variables, separators=(',', ':'))) + '&extensions='  + quote_plus(json.dumps(extensions, separators=(',', ':')))
    gql_json = utils.get_url_json(gql_url, headers=headers)
    if gql_json:
        return gql_json['data']['article'], headers
    return None, headers


def get_channel_feed(slug, tenant, headers={}):
    if not headers:
        headers = get_bolt_headers()

    # headers['accept'] = '*/*'
    headers['sec-fetch-site'] = 'cross-site'

    variables = {
        "slug": slug,
        "tenant": tenant,
        "filter": "Home",
        "first": 20
    }
    # Query hashes are in https://bleacherreport.com/_next/static/chunks/14141-ee0d12dd47b557fc.js
    extensions = {
        "persistedQuery": {
            "version": 1,
            "sha256Hash": "500ec5c7f7bb769802b7135de3cd6753e62e65dcd0471a6c80b3d362cb14676d"
        }
    }
    gql_url = 'https://fed-api.sportsplatform.io/graphql?operationName=GetChannelCommunityContentFeed&variables=' + quote_plus(json.dumps(variables, separators=(',', ':'))) + '&extensions='  + quote_plus(json.dumps(extensions, separators=(',', ':')))
    gql_json = utils.get_url_json(gql_url, headers=headers)
    if gql_json:
        return gql_json['data']['communityContentFeed'], headers
    return None, headers


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))

    if 'post' in paths:
        post_json = utils.get_url_json('https://layserbeam-cached.bleacherreport.com/djay/content?url=' + quote_plus(url))
        if not post_json:
            return None
        return get_track_content(post_json['tracks'][0], args, site_json, save_debug)

    if 'user_post' in paths:
        return get_user_post(url, args, site_json, save_debug)

    m = re.search(r'/articles/(\d+)', url)
    if not m:
        logger.warning('unhandled url ' + url)
        return None

    # article_json = utils.get_url_json('https://layserbeam-cached.bleacherreport.com/articles/' + m.group(1))
    article_json, headers = get_article(m.group(1), site_json['tenant'])
    if not article_json:
        return None
    return get_item(article_json, args, site_json, save_debug)


def get_item(article_json, args, site_json, save_debug):
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')
    item = {}
    item['id'] = article_json['displayId']
    item['url'] = 'https://' + site_json['netloc'] + article_json['slug']
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['publishedDateTime'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('updatedAt'):
        dt = datetime.fromisoformat(article_json['updatedAt'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {
        "name": article_json['author']['name']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    if article_json.get('tags'):
        item['tags'] = [x['displayName'] for x in article_json['tags']]

    if article_json.get('image'):
        item['image'] = article_json['image']['url']

    if article_json.get('description'):
        item['summary'] = article_json['description']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] = ''
    if article_json.get('slides'):
        for slide in article_json['slides']:
            if slide.get('title'):
                if re.sub(r'\W', '', slide['title']).lower() != re.sub(r'\W', '', item['title']).lower():
                    item['content_html'] += '<h2>' + slide['title'] + '</h2>'
            # if slide.get('featuredMedia'):
            #     item['content_html'] += format_element(slide['featuredMedia'])
            if slide.get('elements'):
                for element in slide['elements']:
                    item['content_html'] += format_element(element)

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(div|figure|table|/li)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path.split('/')))
    channel_feed, headers = get_channel_feed(paths[-1], site_json['tenant'])
    if not channel_feed:
        return None

    if save_debug:
        utils.write_file(channel_feed, './debug/feed.json')

    def get_node_item(node):
        nonlocal headers
        nonlocal site_json
        item = {}
        if node['type'] == 'Article':
            article_url = 'https://' + site_json['netloc'] + node['content']['slug']
            if save_debug:
                logger.debug('getting content for ' + article_url)
            m = re.search(r'/articles/(\d+)', article_url)
            if not m:
                logger.warning('unhandled url ' + article_url)
                return None
            article_json, headers = get_article(m.group(1), site_json['tenant'], headers)
            if article_json:
                item = get_item(article_json, args, site_json, save_debug)
        elif node['type'] == 'VideoV2':
            video_id = node['content']['offering']['editId']
            if save_debug:
                logger.debug('getting VideoV2 content for ' + video_id)
            video_json, headers = get_video_v2(video_id, headers)
            if not video_json:
                logger.warning('unable to get VideoV2 content for ' + node['content']['offering']['editId'])
                return None
            if save_debug:
                utils.write_file(video_json, './debug/video.json')
            item['id'] = video_id
            # TODO: not a direct url
            item['url'] = 'https://www.bleacherreport.com/video/' + video_id
            item['title'] = node['title']
            # TODO: check timezone
            dt = datetime.fromtimestamp(int(node['content']['createdDateTime'])).replace(tzinfo=timezone.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
            item['author'] = {
                "name": "Bleacher Report"
            }
            item['authors'] = []
            item['authors'].append(item['author'])
            item['image'] = node['thumbnail']
            item['summary'] = node['description']
            item['_video'] = video_json['manifest']['url']
            if video_json['manifest']['format'] == 'dash':
                item['_video_type'] = 'application/dash+xml'
            else:
                logger.warning('unhandled video type {} for {}'.format(video_json['manifest']['format'], item['url']))
            item['content_html'] = utils.add_video(item['_video'], item['_video_type'], item['image'], item['title'])
        else:
            logger.warning('unhandled feed content type ' + edge['node']['type'])
            return None
        return item

    n = 0
    feed_items = []
    for grouping in channel_feed['groupings']:
        for component in grouping['components']:
            if component['semanticID'] == 'ContentCommunityFeed':
                for edge in component['contentsConnection']['edges']:
                    node = edge['node']
                    item = {}
                    if node['__typename'] == 'StandaloneContentModule':
                        item = get_node_item(node)
                    elif node['__typename'] == 'PackageContentModule':
                        for content in node['contents']:
                            if node['__typename'] == 'StandaloneContentModule':
                                item = get_node_item(node)
                    else:
                        logger.warning('unhandled node __typename {} in {}'.format(node['__typename'], url))
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
