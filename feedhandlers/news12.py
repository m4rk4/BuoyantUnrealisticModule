import json, re
from datetime import datetime
from urllib.parse import urlsplit

from feedhandlers import dirt, rss
import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "priority": "u=1, i",
        "rsc": "1",
        "sec-ch-ua": "\"Chromium\";v=\"124\", \"Microsoft Edge\";v=\"124\", \"Not-A.Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }
    next_data = utils.get_url_html(url, headers=headers)
    if not next_data:
        logger.warning('unable to get next data from ' + url)
        return None
    if save_debug:
        utils.write_file(next_data, './debug/next.txt')

    next_json = None
    for line in next_data.splitlines():
        if '"story":' in line:
            i = line.find('[')
            next_json = json.loads(line[i:])
            break

    if not next_json:
        logger.warning('unable to find story in next data for ' + url)
        return None
    if save_debug:
        utils.write_file(next_json, './debug/debug.json')

    story_json = None
    for it in next_json:
        if it[3].get('story'):
            story_json = it[3]['story']
            break
    if not next_json:
        logger.warning('unable to find story in next data for ' + url)
        return None
    if save_debug:
        utils.write_file(story_json, './debug/debug.json')

    item = {}
    item['id'] = story_json['id']
    item['url'] = 'https://{}/{}'.format(urlsplit(url).netloc, story_json['slug'])
    item['title'] = story_json['title']

    dt = datetime.fromisoformat(story_json['originalPublishedAt'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(story_json['publishedAt'])
    item['date_modified'] = dt.isoformat()

    if story_json.get('authorsData'):
        authors = []
        for it in story_json['authorsData']:
            authors.append(it['name'])
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif story_json.get('authors'):
        item['author'] = {"name": story_json['authors']}

    item['tags'] = []
    if story_json.get('categories'):
        for it in story_json['categories']:
            item['tags'].append(it['name'])
    if story_json.get('keywords'):
        item['tags'] += story_json['keywords'].copy()

    if story_json.get('heroImage'):
        item['_image'] = story_json['heroImage']
    elif story_json.get('metadata') and story_json['metadata'].get('thumbnailUrl'):
        item['_image'] = story_json['metadata']['thumbnailUrl']

    if story_json.get('description'):
        item['summary'] = story_json['description']

    item['content_html'] = ''
    if story_json.get('videoFile'):
        video = next((it for it in story_json['videoFile']['videoUrls'] if it['mime'] == 'application/x-mpegURL'), None)
        if not video:
            video = next((it for it in story_json['videoFile']['videoUrls'] if it['mime'] == 'video/mp4'), None)
        image = next((it for it in story_json['videoFile']['videoUrls'] if it['mime'] == 'image/jpeg'), None)
        if image:
            poster = image['url']
        else:
            poster = item['_image']
        item['content_html'] += utils.add_video(video['url'], video['mime'], poster)

    for content in story_json['content']['content']:
        item['content_html'] += dirt.render_content(content, None)

    return item
