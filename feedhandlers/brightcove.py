import re, requests
from datetime import datetime

import utils

import logging

logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
    s = requests.Session()
    r = s.get(url)
    if not r:
        return None
    m = re.search(r'policyKey:"([^"]+)"', r.text)
    if not m:
        logger.warning('unable to find policyKey in ' + url)
        return None
    headers = {
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "sec-ch-ua": "\"Chromium\";v=\"104\", \" Not A;Brand\";v=\"99\", \"Microsoft Edge\";v=\"104\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site"
    }
    headers['accept'] = 'application/json;pk={}'.format(m.group(1))

    # https://players.brightcove.net/1105443290001/19b4b681-5e7c-4b03-b1ff-050f00d0be3e_default/index.html?videoId=6294188220001
    m = re.search(r'https:\/\/players\.brightcove\.net\/(\d+)\/.*videoId=(\d+)', url)
    if not m:
        logger.warning('unsupported brightcove url ' + url)
        return None
    api_url = 'https://edge.api.brightcove.com/playback/v1/accounts/{}/videos/{}'.format(m.group(1), m.group(2), headers=headers)
    r = s.get(api_url, headers=headers)

    item = {}
    item['id'] = m.group(2)
    item['url'] = url

    if r.status_code == 403:
        video_json = r.json()
        item['content_html'] = ''
        if video_json[0].get('error_code'):
            item['content_html'] += '<h3>{}</h3>'.format(video_json[0]['error_code'])
        if video_json[0].get('message'):
            item['content_html'] += '<p>{}</p>'.format(video_json[0]['message'])
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
