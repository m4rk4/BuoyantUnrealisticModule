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
        "sec-ch-ua": "\" Not;A Brand\";v=\"99\", \"Microsoft Edge\";v=\"97\", \"Chromium\";v=\"97\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site"
    }
    headers['Accept'] = 'application/json;pk={}'.format(m.group(1))

    # https://players.brightcove.net/1105443290001/19b4b681-5e7c-4b03-b1ff-050f00d0be3e_default/index.html?videoId=6294188220001
    m = re.search(r'https:\/\/players\.brightcove\.net\/(\d+)\/.*videoId=(\d+)', url)
    if not m:
        logger.warning('unsupported brightcove url ' + url)
        return None
    api_url = 'https://edge.api.brightcove.com/playback/v1/accounts/{}/videos/{}'.format(m.group(1), m.group(2), headers=headers)
    r = s.get(api_url, headers=headers)
    if not r:
        return None
    video_json = r.json()
    if save_debug:
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

    item['author'] = {"name": video_json['account_id']}
    item['_image'] = video_json['poster']
    item['summary'] = video_json['description']

    sources = []
    for source in video_json['sources']:
        if source.get('src') and source.get('container') and source['container'] == 'MP4':
            source['type'] = 'video/mp4'
            sources.append(source)
    if not sources:
        for source in video_json['sources']:
            if source.get('src') and source.get('type') and source['type'] == 'application/x-mpegURL':
                sources.append(source)
    source = utils.closest_dict(sources, 'height', 480)
    item['_video'] = source['src']
    item['content_html'] = utils.add_video(source['src'], source['type'], item['_image'], item['title'])

    if not 'embed' in args:
        item['content_html'] += '<p>{}</p>'.format(item['summary'])

    return item
