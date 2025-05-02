import re, requests
from datetime import datetime
from urllib.parse import quote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)

def get_content(url, args, site_json, save_debug=False):
    s = requests.Session()

    if 'data-key' in args:
        pk = args['data-key']
    else:
        r = s.get(url)
        if not r:
            return None
        m = re.search(r'"?policyKey"?:"([^"]+)"', r.text)
        if not m:
            logger.warning('unable to find policyKey in ' + url)
            return None
        pk = m.group(1)

    # print(pk)
    headers = {
        "accept": "application/json;pk=" + pk,
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Chromium\";v=\"124\", \"Microsoft Edge\";v=\"124\", \"Not-A.Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site"
    }

    video_id = ''
    playlist_id = ''
    if 'data-account' in args and 'data-video-id' in args:
        account = args['data-account']
        video_id = args['data-video-id']
    else:
        # https://players.brightcove.net/1105443290001/19b4b681-5e7c-4b03-b1ff-050f00d0be3e_default/index.html?videoId=6294188220001
        m = re.search(r'https:\/\/players\.brightcove\.net\/(\d+)\/.*(videoId|playlistId)=(\d+)', url, flags=re.I)
        if not m:
            logger.warning('unsupported brightcove url ' + url)
            return None
        account = m.group(1)
        if m.group(2).lower() == 'videoid':
            video_id = m.group(3)
        else:
            playlist_id = m.group(3)

    if not video_id and playlist_id:
        api_url = 'https://edge.api.brightcove.com/playback/v1/accounts/{}/playlists/{}?limit=100'.format(account, playlist_id)
    else:
        api_url = 'https://edge.api.brightcove.com/playback/v1/accounts/{}/videos/{}'.format(account, video_id)

    r = s.get(api_url, headers=headers)
    if r.status_code == 403:
        item = {}
        video_json = r.json()
        msg = ''
        if video_json[0].get('error_code'):
            msg += '<strong>{}</strong>'.format(video_json[0]['error_code'])
        if video_json[0].get('message'):
            if msg:
                msg += ': '
            msg += video_json[0]['message']
        if args.get('poster'):
            if args.get('title'):
                if msg:
                    msg += ' | '
                msg += args['title']
            item['content_html'] = utils.add_image(args['poster'], msg)
        else:
            item['content_html'] = '<blockquote>{}</blockquote>'.format(msg)
        return item
    elif r.status_code != 200:
        logger.warning('status code {} getting {}'.format(r.status_code, api_url))
        return None

    if playlist_id:
        playlist_json = r.json()
        video_json = playlist_json['videos'][0]
    else:
        video_json = r.json()
    if save_debug:
        utils.write_file(video_json, './debug/video.json')
    utils.write_file(video_json, './debug/video.json')

    item = {}
    item['id'] = video_json['id']
    item['url'] = url

    item['title'] = video_json['name']

    dt = datetime.fromisoformat(video_json['created_at'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(video_json['updated_at'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    authors = []
    if video_json.get('custom_fields'):
        for key, val in video_json['custom_fields'].items():
            if key.startswith('author'):
                authors.append(re.sub(r'_\d+$', '', val))
    if authors:
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author']['name'] = video_json['account_id']

    if video_json.get('tags'):
        item['tags'] = video_json['tags'].copy()

    item['_image'] = video_json['poster']
    item['summary'] = video_json['description']

    mp4_sources = []
    m3u8_sources = []
    for source in video_json['sources']:
        if source.get('src') and source.get('container') and source['container'] == 'MP4' and source.get('height'):
            source['type'] = 'video/mp4'
            mp4_sources.append(source)
        elif source.get('src') and source.get('type') and source['type'] == 'application/x-mpegURL':
            m3u8_sources.append(source)

    source = None
    if m3u8_sources:
        source = m3u8_sources[0]
    elif mp4_sources:
        source = utils.closest_dict(mp4_sources, 'height', 480)
        if not source:
            source = mp4_sources[0]

    if args.get('caption'):
        caption = args['caption']
    else:
        caption = item['title']

    if source:
        item['_video'] = source['src']
        item['content_html'] = utils.add_video(source['src'], source['type'], item['_image'], caption)
    else:
        logger.warning('unknown video source for ' + item['url'])
        poster = '{}/image?url={}&width=1200&overlay=video'.format(config.server, quote_plus(item['_image']))
        item['content_html'] = utils.add_image(poster, caption, link=item['url'])

    if not 'embed' in args or 'add_summary' in args:
        item['content_html'] += '<p>{}</p>'.format(item['summary'])
    return item
