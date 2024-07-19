import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import wp_posts

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if paths[0] == 'news' or paths[0] == 'watch':
        prefix = ''
        build_id = site_json['buildId']
    else:
        prefix = '/_teams'
        build_id = site_json['teams_buildId']
    if len(paths) == 0:
        path = '/index'
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
    path += '.json'
    next_url = '{}://{}{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, prefix, build_id, path)
    # print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if not el:
            logger.warning('unable to find __NEXT_DATA__ in ' + url)
            return None
        next_data = json.loads(el.string)
        if next_data['buildId'] != build_id:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            if paths[0] == 'news' or paths[0] == 'watch':
                site_json['buildId'] = next_data['buildId']
            else:
                site_json['teams_buildId'] = next_data['buildId']
            utils.update_sites(url, site_json)
        return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug=False):
    next_data = None
    split_url = urlsplit(url)
    if split_url.netloc == 'watch.nba.com':
        # TODO
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
        next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    if split_url.path.startswith('/news'):
        article_json = next_data['pageProps']['article']
    elif split_url.path.startswith('/watch'):
        article_json = next_data['pageProps']['video']
    else:
        article_json = next_data['pageProps']['pageObject']

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

    if article_json.get('excerpt'):
        item['summary'] = article_json['excerpt']
    elif article_json.get('description'):
        item['summary'] = article_json['description']

    lede_html = ''
    if article_json.get('featuredImage'):
        if isinstance(article_json['featuredImage'], dict):
            item['_image'] = article_json['featuredImage']['attributes']['src']
            captions = []
            if article_json['featuredImage']['attributes'].get('caption'):
                captions.append(article_json['featuredImage']['attributes']['caption'])
            if article_json['featuredImage']['attributes'].get('credit'):
                captions.append(article_json['featuredImage']['attributes']['credit'])
            lede_html += utils.add_image(item['_image'], ' | '.join(captions))
        else:
            item['_image'] = article_json['featuredImage']
    elif article_json.get('image'):
        item['_image'] = article_json['image']

    if article_json['type'] == 'gallery' and article_json.get('galleryDefaults'):
        lede_html += '<p><em>{} | Credit: {}</em></p>'.format(article_json['galleryDefaults']['caption'], article_json['galleryDefaults']['credit'])

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
        item['content_html'] = ''
        if article_json.get('excerpt'):
            item['content_html'] += '<p><em>' + article_json['excerpt'] + '</em></p>'
        if lede_html:
            item['content_html'] += lede_html
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
        item['content_html'] = ''
        if article_json.get('excerpt'):
            item['content_html'] += '<p><em>' + article_json['excerpt'] + '</em></p>'
        item['content_html'] += wp_posts.format_content(article_json['contentFiltered'], item, site_json)

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://content-api-prod.nba.com/public/1/leagues/nba/content?page=1&count=10&types=post&region=united-states
    # https://www.nba.com/cavaliers/api/content/category/news?page=1

    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')
