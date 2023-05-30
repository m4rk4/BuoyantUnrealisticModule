import re
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1080):
    # https://themessenger.com/_next/image?url=https%3A%2F%2Fcms.themessenger.com%2Fwp-content%2Fuploads%2F2023%2F05%2FGettyImages-1396387041-scaled.jpg&w=1080&q=75
    return 'https://themessenger.com/_next/image?url={}&w={}&q=75'.format(quote_plus(img_src), width)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    if len(paths) == 0:
        path = '/index'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    path += '.json'

    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        m = re.search(r'"buildId":"([^"]+)"', page_html)
        if m and m.group(1) != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = m.group(1)
            utils.update_sites(url, site_json)
            next_url = '{}://{}/_next/data/{}/{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
            next_data = utils.get_url_json(next_url)
            if not next_data:
                return None
    return next_data


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    post_json = next_data['pageProps']['post']
    item = {}
    item['id'] = post_json['id']
    item['url'] = url
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['date'] + '+00:00')
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['modified'] + '+00:00')
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    item['author']['name'] = '{} {}'.format(post_json['author']['node']['firstName'], post_json['author']['node']['lastName'])

    item['tags'] = []
    if post_json.get('categories') and post_json['categories'].get('edges'):
        for it in post_json['categories']['edges']:
            item['tags'].append(it['node']['name'])
    if post_json.get('tags') and post_json['tags'].get('nodes'):
        for it in post_json['tags']['nodes']:
            item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''
    if post_json['story'].get('subHead'):
        item['content_html'] += '<p><em>{}</em></p>'.format(post_json['story']['subHead'])

    if post_json.get('featuredImage') and post_json['featuredImage'].get('node'):
        image_node = post_json['featuredImage']['node']
        item['_image'] = image_node['sourceUrl']
        if image_node.get('mediaOptions') and image_node['mediaOptions'].get('mediaCredit'):
            caption = image_node['mediaOptions']['mediaCredit']
        else:
            caption = ''
        item['content_html'] += utils.add_image(resize_image(image_node['sourceUrl']), caption)

    for block in post_json['blocks']:
        if block['__typename'] == 'CoreParagraphBlock' or block['__typename'] == 'CoreListBlock':
            item['content_html'] += block['saveContent']
        elif block['__typename'] == 'CoreHeadingBlock':
            item['content_html'] += '<h{0}>{1}</h{0}>'.format(block['attributes']['level'], block['attributes']['content'])
        elif block['__typename'] == 'CoreImageBlock':
            item['content_html'] += utils.add_image(resize_image(block['attributes']['url']), block['attributes'].get('caption'))
        elif block['__typename'] == 'CoreEmbedBlock':
            item['content_html'] += utils.add_embed(block['attributes']['url'])
        else:
            logger.warning('unhandled block type {} in {}'.format(block['__typename'], item['url']))

    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
