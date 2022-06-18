import re
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

from feedhandlers import fusion, nextjs, rss
import utils

import logging

logger = logging.getLogger(__name__)


def resize_image(image_item, width_target):
    return 'https://www.washingtonpost.com/wp-apps/imrs.php?src={}&w={}'.format(quote_plus(image_item['url']), width_target)


def get_item(content, url, args, save_debug):
    item = {}
    item['id'] = content['_id']

    if content.get('additional_properties') and content['additional_properties'].get('permalinkUrl'):
        item['url'] = content['additional_properties']['permalinkUrl']
    else:
        split_url = urlsplit(url)
        item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, content['canonical_url'])

    item['title'] = content['headlines']['basic']

    dt = datetime.fromisoformat(content['first_publish_date'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(content['last_updated_date'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    authors = []
    for byline in content['credits']['by']:
        authors.append(byline['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if content['taxonomy'].get('seo_keywords'):
        item['tags'] = content['taxonomy']['seo_keywords'].copy()
    elif content['tracking'].get('content_topics'):
        item['tags'] = content['tracking']['content_topics'].split(';')

    if content.get('promo_items') and content['promo_items']['basic']['type'] == 'image':
        item['_image'] = content['promo_items']['basic']['url']

    item['summary'] = content['description']['basic']

    if content['type'] == 'video':
        streams = []
        for stream in content['streams']:
            if stream['stream_type'] == 'mp4':
                streams.append(stream)
        stream = utils.closest_dict(streams, 'height', 720)
        item['content_html'] = utils.add_video(stream['url'], 'video/mp4', item['_image'])
        if 'embed' not in args:
            item['content_html'] += '<p>{}</p>'.format(item['summary'])
    else:
        item['content_html'] = fusion.get_content_html(content, resize_image, url, save_debug)
    return item


def get_content(url, args, save_debug=False):
    next_json = nextjs.get_next_data_json(url, save_debug, 'mobile')
    if not next_json:
        return None
    if '/video/' in url:
        if next_json['props']['pageProps'].get('videoData'):
            content = next_json['props']['pageProps']['videoData']
        else:
            content = next_json['props']['pageProps']['playlist'][0]
    else:
        content = next_json['props']['pageProps']['globalContent']

    if save_debug:
        utils.write_file(content, './debug/debug.json')

    return get_item(content, url, args, save_debug)


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
