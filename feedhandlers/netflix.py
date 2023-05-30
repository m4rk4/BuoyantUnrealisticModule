import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1080):
    return 'https://www.whynow.co.uk/_next/image?url={}&w={}&q=75'.format(quote_plus(img_src), width)


def get_video_src(video_id):
    # TODO: what is id? Seems to partly be a timestamp
    json_data = {
        "version": 2,
        "url": "manifest",
        "id": 168254571767704770,
        "languages": ["en-US"],
        "params": {
            "type": "standard",
            "manifestVersion": "v2",
            "viewableId": video_id,
            "profiles": [
                "heaac-2-dash",
                "heaac-2hq-dash",
                "playready-h264mpl30-dash",
                "playready-h264mpl31-dash",
                "playready-h264mpl40-dash",
                "playready-h264hpl30-dash",
                "playready-h264hpl31-dash",
                "playready-h264hpl40-dash",
                "h264hpl30-dash-playready-live",
                "h264hpl31-dash-playready-live",
                "h264hpl40-dash-playready-live",
                "dfxp-ls-sdh",
                "simplesdh",
                "nflx-cmisc",
                "imsc1.1",
                "BIF240",
                "BIF320"
            ],
            "flavor": "STANDARD",
            "drmType": "playready",
            "drmVersion": 30,
            "usePsshBox": True,
            "isBranching": False,
            "useHttpsStreams": True,
            "supportsUnequalizedDownloadables": True,
            "imageSubtitleHeight": 1080,
            "uiVersion": "shakti-pulse-vac98072c",
            "uiPlatform": "",
            "clientVersion": "6.0039.848.911",
            "platform": "112.0.1722",
            "osVersion": "10.0",
            "osName": "windows",
            "supportsPreReleasePin": True,
            "supportsWatermark": True,
            "videoOutputInfo": [
                {
                    "type": "DigitalVideoOutputDescriptor",
                    "outputType": "unknown",
                    "supportedHdcpVersions": ["1.4"],
                    "isHdcpEngaged": True
                }
            ],
            "titleSpecificData": {
                str(video_id): {
                    "unletterboxed": False
                }
            },
            "preferAssistiveAudio": False,
            "isUIAutoPlay": False,
            "isNonMember": False,
            "desiredVmaf": "plus_lts",
            "desiredSegmentVmaf": "plus_lts",
            "requestSegmentVmaf": False,
            "supportsPartialHydration": True,
            "contentPlaygraph": [],
            "supportsAdBreakHydration": False,
            "liveMetadataFormat": "INDEXED_SEGMENT_TEMPLATE",
            "useBetterTextUrls": True
        }
    }
    api_url = 'https://www.netflix.com/playapi/cadmium/manifest/1?reqAttempt=1&reqName=manifest&clienttype=akira&uiversion=pulse-vac98072c&browsername=edgeoss&browserversion=112.0.1722&osname=windows&osversion=10.0'
    video_json = utils.post_url(api_url, json_data=json_data)
    if not video_json:
        return ''
    utils.write_file(video_json, './debug/video.json')
    return video_json['video_tracks'][0]['streams'][0]['urls'][0]['url']


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if paths[0] != 'tudum':
        logger.warning('unhandled url ' + url)
        return None

    json_data = {
        "operationName": "PulsePageQuery",
        "variables":{
            "withProfile": False,
            "url": '/' + '/'.join(paths[1:])
        },
        "extensions": {
            "persistedQuery": {
                "version":1,
                "sha256Hash":"426c651cce64f4575f839beba6b651f938019e47b3ff23758a670986621ae9a8"
            }
        }
    }
    gql_json = utils.post_url('https://pulse.prod.cloud.netflix.com/graphql', json_data=json_data)
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')

    page_json = gql_json['data']['pulsePage']
    article_json = next((it for it in page_json['seo']['structuredSchemas'] if (it['__typename'] == 'PulsePageSEOStructuredNewsArticleSchemaObject' or it['__typename'] == 'PulsePageSEOStructuredArticleSchema')), None)

    item = {}
    item['id'] = page_json['pageId']
    item['url'] = url
    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['publishedAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['modifiedAt'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    if article_json.get('authors'):
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(article_json['authors']))

    if article_json.get('featuredImage'):
        item['_image'] = article_json['featuredImage']['url']

    if page_json['seo'].get('description'):
        item['summary'] = page_json['seo']['description']

    item['content_html'] = ''
    for section in page_json['sections']:
        if section.get('guid'):
            if section['guid'] == 'topic-pills':
                item['tags'] = []
                for entity in section['entities']:
                    if entity['__typename'] == 'PulseLinkEntity':
                        item['tags'].append(entity['text'])
            continue
        for entity in section['entities']:
            if entity['__typename'] == 'PulseHtmlRichTextEntity':
                soup = BeautifulSoup(entity['html'], 'html.parser')

                if entity.get('imageReferences'):
                    for img in entity['imageReferences']:
                        new_html = ''
                        el = soup.find(attrs={"asset-id": img['assetId']})
                        if el:
                            if el.parent and el.parent.name == 'media-card':
                                card = el.parent
                            else:
                                card = el
                            captions = []
                            it = card.find(re.compile('image-caption'))
                            if it:
                                captions.append(it.decode_contents())
                            if el.get('credits'):
                                captions.append(el['credits'])
                            new_html = utils.add_image(img['image']['url'], ' | '.join(captions))
                        if new_html:
                            new_el = BeautifulSoup(new_html, 'html.parser')
                            el.insert_after(new_el)
                            el.decompose()
                        else:
                            logger.warning('unhandled imageReference assetId {} in {}'.format(img['assetId'], item['url']))
                for el in soup.find_all('third-party-embed'):
                    new_html = utils.add_embed(el['url'])
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_after(new_el)
                    el.decompose()
                for el in soup.find_all('embedded-entry'):
                    el.decompose()
                item['content_html'] += str(soup)
            elif entity['__typename'] == 'PulseArticleHeroEntity':
                if entity.get('bodyRichText'):
                    item['content_html'] += '<p><em>{}</em></p>'.format(entity['bodyRichText']['html'])
                if entity.get('backgroundImage'):
                    item['content_html'] += utils.add_image(entity['backgroundImage']['url'], entity.get('imageCredit'))
            # elif entity['__typename'] == 'PulseVideoPlayerEntity':
            #     video_src = get_video_src(entity['videoID'])
            #     if video_src:
            #         item['content_html'] += utils.add_video(video_src, 'application/x-mpegURL',  entity['image']['url'])
            else:
                logger.warning('unhandled entity {} in {}'.format(entity['__typename'], item['url']))
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if paths[0] != 'tudum':
        logger.warning('unhandled url ' + url)
        return None

    json_data = {
        "operationName": "PulsePageQuery",
        "variables":{
            "withProfile": False,
            "url": '/' + '/'.join(paths[1:])
        },
        "extensions": {
            "persistedQuery": {
                "version":1,
                "sha256Hash":"426c651cce64f4575f839beba6b651f938019e47b3ff23758a670986621ae9a8"
            }
        }
    }
    gql_json = utils.post_url('https://pulse.prod.cloud.netflix.com/graphql', json_data=json_data)
    if save_debug:
        utils.write_file(gql_json, './debug/feed.json')


    n = 0
    feed_items = []
    for section in gql_json['data']['pulsePage']['sections']:
        for entity in section['entities']:
            if entity['__typename'] == 'PulseArticleItemEntity':
                entity_url = 'https://www.netflix.com/tudum' + entity['slug']
                if save_debug:
                    logger.debug('getting content for ' + entity_url)
                item = get_content(entity_url, args, site_json, save_debug)
                if item:
                    if utils.filter_item(item, args) == True:
                        feed_items.append(item)
                        n += 1
                        if 'max' in args:
                            if n == int(args['max']):
                                break

    feed = utils.init_jsonfeed(args)
    #feed['title'] = soup.title.get_text()
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
