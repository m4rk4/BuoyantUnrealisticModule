import re
from datetime import datetime

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    m = re.search(r'documentcloud\.org/documents/(\d+)', url)
    if not m:
        logger.warning('unhandled url ' + url)
        return None
    api_url = 'https://api.www.documentcloud.org/api/documents/{}/?expand=user%2Corganization%2Cnotes%2Csections%2Cnotes.organization%2Cnotes.user&format=json'.format(m.group(1))
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/content.json')

    item = {}
    item['id'] = api_json['id']
    item['url'] = api_json['canonical_url']
    item['title'] = api_json['title']

    dt = datetime.fromisoformat(api_json['created_at'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(api_json['updated_at'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()
    ts = int(dt.timestamp() * 1000)

    item['author'] = {}
    item['author']['name'] = api_json['user']['name']
    if api_json.get('organization') and not api_json['organization']['individual']:
        item['author']['name'] += ' ({})'.format(api_json['organization']['name'])

    item['_image'] = 'https://s3.documentcloud.org/documents/{}/pages/{}-p1-normal.gif?ts={}'.format(api_json['id'], api_json['slug'], ts)

    attachment = {}
    attachment['url'] = 'https://s3.documentcloud.org/documents/{}/{}.pdf'.format(api_json['id'], api_json['slug'])
    attachment['mime_type'] = 'application/pdf'
    item['attachments'] = []
    item['attachments'].append(attachment)

    caption = item['title']
    if api_json.get('source'):
        caption += ' (Source: {})'.format(api_json['source'])
    caption += '. <a href="{}">View the pdf</a>.'.format(attachment['url'])

    item['content_html'] = utils.add_image(item['_image'], caption, link=item['url'])
    return item
