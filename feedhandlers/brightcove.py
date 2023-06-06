import re, requests
from datetime import datetime

import utils

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
        m = re.search(r'policyKey:"([^"]+)"', r.text)
        if not m:
            logger.warning('unable to find policyKey in ' + url)
            return None
        pk = m.group(1)
    headers = {
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"113\", \"Chromium\";v=\"113\", \"Not-A.Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site"
    }
    headers['accept'] = 'application/json;pk={}'.format(pk)

    if 'data-account' in args and 'data-video-id' in args:
        account = args['data-account']
        video_id = args['data-video-id']
    else:
        # https://players.brightcove.net/1105443290001/19b4b681-5e7c-4b03-b1ff-050f00d0be3e_default/index.html?videoId=6294188220001
        m = re.search(r'https:\/\/players\.brightcove\.net\/(\d+)\/.*videoId=(\d+)', url)
        if not m:
            logger.warning('unsupported brightcove url ' + url)
            return None
        account = m.group(1)
        video_id = m.group(2)

    api_url = 'https://edge.api.brightcove.com/playback/v1/accounts/{}/videos/{}'.format(account, video_id)
    r = s.get(api_url, headers=headers)

    item = {}
    item['id'] = video_id
    item['url'] = url

    if r.status_code == 403:
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
        return None

    video_json = r.json()
    if save_debug:
        utils.write_file(video_json, './debug/video.json')

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

    sources = []
    for source in video_json['sources']:
        if source.get('src') and source.get('container') and source['container'] == 'MP4' and source.get('height'):
            source['type'] = 'video/mp4'
            sources.append(source)
    if not sources:
        for source in video_json['sources']:
            if source.get('src') and source.get('type') and source['type'] == 'application/x-mpegURL':
                sources.append(source)
    try:
        source = utils.closest_dict(sources, 'height', 480)
    except:
        source = sources[0]
    item['_video'] = source['src']
    item['content_html'] = utils.add_video(source['src'], source['type'], item['_image'], item['title'])

    if not 'embed' in args:
        item['content_html'] += '<p>{}</p>'.format(item['summary'])

    return item
