import re, tldextract
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_build_id(url):
    page_html = utils.get_url_html(url)
    m = re.search(r'"buildId":"([^"]+)"', page_html)
    if not m:
        return ''
    return m.group(1)


def get_next_json(url):
    tld = tldextract.extract(url)
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    if path:
        path += '.json'
    else:
        path = '/index.json'

    sites_json = utils.read_json_file('./sites.json')
    if paths[0] == 'news' or paths[0] == 'watch':
        prefix = ''
        build_id = sites_json[tld.domain]['buildId']
    else:
        prefix = '/_teams'
        build_id = sites_json[tld.domain]['teams_buildId']

    next_url = '{}://{}{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, prefix, build_id, path)
    next_json = utils.get_url_json(next_url, retries=1)
    if not next_json:
        # Try updating the build id
        logger.debug('updating buildId for ' + url)
        new_build_id = get_build_id(url)
        if new_build_id != build_id:
            if prefix:
                sites_json[tld.domain]['teams_buildId'] = new_build_id
            else:
                sites_json[tld.domain]['buildId'] = new_build_id
            utils.write_file(sites_json, './sites.json')
            next_url = '{}://{}{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, prefix, new_build_id, path)
            next_json = utils.get_url_json(next_url, retries=1)
    return next_json


def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    sites_json = utils.read_json_file('./sites.json')
    tld = tldextract.extract(url)

    next_json = None
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
    else:
        next_json = get_next_json(url)
    if not next_json:
        return None

    if split_url.path.startswith('/news'):
        article_json = next_json['pageProps']['article']
    elif split_url.path.startswith('/watch'):
        article_json = next_json['pageProps']['video']
    else:
        article_json = next_json['pageProps']['pageObject']
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
    dt = datetime.fromisoformat(article_json['date'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['modified'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('author'):
        if article_json['author'].get('firstName') and article_json['author'].get('lastName'):
            item['author']['name'] = '{} {}'.format(article_json['author']['firstName'], article_json['author']['lastName'])
        else:
            item['author']['name'] = article_json['author']['name']
    else:
        item['author']['name'] = 'NBA.com'

    item['tags'] = []
    for val in article_json['taxonomy'].values():
        if isinstance(val, dict):
            for v in val.values():
                if isinstance(v, str) and v not in item['tags']:
                    item['tags'].append(v)

    lede_html = ''
    if article_json.get('featuredImage'):
        if isinstance(article_json['featuredImage'], dict):
            item['_image'] = article_json['featuredImage']['attributes']['src']
            captions = []
            if article_json['featuredImage']['attributes'].get('caption'):
                captions.append(article_json['featuredImage']['attributes']['caption'])
            if article_json['featuredImage']['attributes'].get('credit'):
                captions.append(article_json['featuredImage']['attributes']['credit'])
            lede_html = utils.add_image(item['_image'], ' | '.join(captions))
        else:
            item['_image'] = article_json['featuredImage']
    elif article_json.get('image'):
        item['_image'] = article_json['image']

    if article_json['type'] == 'gallery' and article_json.get('galleryDefaults'):
        lede_html = '<p><em>{} | Credit: {}</em></p>'.format(article_json['galleryDefaults']['caption'], article_json['galleryDefaults']['credit'])

    if article_json.get('excerpt'):
        item['summary'] = article_json['excerpt']
    elif article_json.get('description'):
        item['summary'] = article_json['description']

    if article_json['type'] == 'video':
        if article_json.get('videoAssets'):
            videos = []
            for video in article_json['videoAssets'].values():
                if isinstance(video, dict) and video.get('video'):
                    videos.append(video)
            video = utils.closest_dict(videos, 'height', 480)
            if '.mp4' in video['video']:
                video_type = 'video/mp4'
            else:
                video_type = 'application/x-mpegURL'
            item['content_html'] = utils.add_video(video['video'], video_type, video['thumbnail'])
            if article_json.get('description'):
                item['content_html'] += '<p>{}</p>'.format(article_json['description'])
        else:
            # FIXME: This video playback doesn't work
            identity_json = utils.get_url_json('https://identity.nba.com/api/v1/sts')
            if identity_json:
                headers = {
                    "accept": "*/*",
                    "accept-language": "en-US,en;q=0.9,de;q=0.8",
                    "authorization": "OAUTH2 access_token=\"{}\"".format(identity_json['data']['AccessToken']),
                    "content-type": "application/json",
                    "sec-ch-ua": "\"Microsoft Edge\";v=\"105\", \"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"105\"",
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": "\"Windows\"",
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-site"
                }
                api_url = 'https://ottapp-appgw-client.nba.com/S1/subscriber/v3/programs/{}/play-options'.format(article_json['mediakindExternalProgramId'])
                api_json = utils.get_url_json(api_url, headers=headers)
                if api_json:
                    utils.write_file(api_json, './debug/video.json')
                    item['content_html'] = utils.add_video(api_json['Vods'][0]['PlayActions'][0]['VideoProfile']['PlaybackUri'], 'application/x-mpegURL', item['_image'], item['summary'])
                else:
                    logger.warning('unable to get video from ' + api_url)
            else:
                logger.warning('unable to get access token from https://watch.nba.com/secure/accesstoken?format=json')
    elif article_json.get('contentStructured'):
        if lede_html:
            item['content_html'] = lede_html
        else:
            item['content_html'] = ''
        for content in article_json['contentStructured']:
            if content['type'] == 'paragraph':
                item['content_html'] += content['html']
            elif content['type'] == 'list':
                item['content_html'] += content['html']
            elif content['type'] == 'image':
                captions = []
                if content['attributes'].get('caption'):
                    captions.append(content['attributes']['caption'])
                if content['attributes'].get('credit'):
                    captions.append(content['attributes']['credit'])
                item['content_html'] += utils.add_image(content['attributes']['src'], ' | '.join(captions))
            elif content['type'] == 'twitter' or content['type'] == 'spotify':
                item['content_html'] += utils.add_embed(content['attributes']['url'])
            else:
                logger.warning('unhandled content type {} in {}'.format(content['type'], item['url']))
    elif article_json.get('contentFiltered'):
        item['content_html'] = wp_posts.format_content(article_json['contentFiltered'], item)

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item
