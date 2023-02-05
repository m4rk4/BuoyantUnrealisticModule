import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    if img_src.startswith('https://qtxasset.com'):
        return 'https://qtxasset.com/cdn-cgi/image/w=1000,f=auto/' + img_src
    return img_src


def add_image(media_data, caption=None):
    media_url = media_data['links']['self']['href']
    if media_data['type'] != 'media--image':
        logger.warning('unsupported media type {}'.format(media_data['type'], media_url))
    split_url = urlsplit(media_url)
    root_url = '{}://{}'.format(split_url.scheme, split_url.netloc)
    file_json = get_jsonapi_data(root_url, media_data['relationships']['field_media_image']['data']['type'], media_data['relationships']['field_media_image']['data']['id'])
    if not file_json:
        return ''
    img_src = resize_image(file_json['data']['attributes']['uri']['url'])
    captions = []
    if caption:
        captions.append(caption.strip())
    if media_data['attributes'].get('field_attribution'):
        captions.append(media_data['attributes']['field_attribution'])
    return utils.add_image(img_src, ' | '.join(captions))


def get_jsonapi_data(root_url, data_type, id, query=''):
    api_url = root_url + '/jsonapi/' + data_type.replace('--', '/') + '/' + id
    if query:
        api_url += '?' + query
    return utils.get_url_json(api_url)


def get_content(url, args, site_json, save_debug):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None

    m = re.search(r'data-uuid="([^"]+)"', page_html)
    if not m:
        logger.warning('unable to determine data-uuid in ' + url)
        return None

    split_url = urlsplit(url)
    root_url = '{}://{}'.format(split_url.scheme, split_url.netloc)
    query = 'include=field_author,field_cat_primary,field_cat_related,field_keywords,field_media'
    api_json = get_jsonapi_data(root_url, 'node--article', m.group(1), query)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    item = {}
    item['id'] = api_json['data']['id']
    item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, api_json['data']['attributes']['path']['alias'])
    item['title'] = api_json['data']['attributes']['title']

    dt = datetime.fromisoformat(api_json['data']['attributes']['created'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(api_json['data']['attributes']['changed'])
    item['date_modified'] = dt.isoformat()

    authors = []
    item['tags'] = []
    media_data = None
    if api_json.get('included'):
        for it in api_json['included']:
            if it['type'] == 'node--person':
                authors.append(it['attributes']['title'])
            elif it['type'].startswith('taxonomy_term'):
                item['tags'].append(it['attributes']['name'])
            elif it['type'].startswith('media--image'):
                media = it

    if not authors and api_json['data']['relationships'].get('field_author'):
        for it in api_json['data']['relationships']['field_author']['data']:
            it_json = get_jsonapi_data(root_url, it['type'], it['id'])
            if it_json:
                authors.append(it_json['data']['attributes']['title'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if not item.get('tags'):
        if api_json['data']['relationships'].get('field_cat_primary'):
            it_json = get_jsonapi_data(root_url, api_json['data']['relationships']['field_cat_primary']['data']['type'], api_json['data']['relationships']['field_cat_primary']['data']['id'])
            if it_json:
                item['tags'].append(it_json['data']['attributes']['name'])
        if api_json['data']['relationships'].get('field_cat_related'):
            for it in api_json['data']['relationships']['field_cat_related']['data']:
                it_json = get_jsonapi_data(root_url, it['type'], it['id'])
                if it_json:
                    item['tags'].append(it_json['data']['attributes']['name'])
        if api_json['data']['relationships'].get('field_keywords'):
            for it in api_json['data']['relationships']['field_keywords']['data']:
                it_json = get_jsonapi_data(root_url, it['type'], it['id'])
                if it_json:
                    item['tags'].append(it_json['data']['attributes']['name'])
    if not item.get('tags'):
        del item['tags']

    content_html = ''
    if not media_data:
        if api_json['data']['relationships'].get('field_media'):
            media_json = get_jsonapi_data(root_url, api_json['data']['relationships']['field_media']['data']['type'], api_json['data']['relationships']['field_media']['data']['id'])
            if media_json:
                media_data = media_json['data']

    if media_data:
        caption = api_json['data']['attributes'].get('field_caption')
        content_html += add_image(media_data, caption)
        m = re.search(r'src="([^"]+)"', content_html)
        item['_image'] = m.group(1)

    if api_json['data']['attributes'].get('field_fronts_teaser'):
        item['summary'] = api_json['data']['attributes']['field_fronts_teaser']

    content_html += api_json['data']['attributes']['body']['value'].replace('<p>&nbsp;</p>', '')
    soup = BeautifulSoup(content_html, 'html.parser')
    for el in soup.find_all(re.compile(r'^drupal-')):
        if el.name == 'drupal-media':
            media_json = get_jsonapi_data(root_url, 'media--image', el['data-entity-uuid'])
            caption = el.get('data-caption')
            media_html = add_image(media_json['data'], caption)
            if media_html:
                new_el = BeautifulSoup(media_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled drupal-media in ' + item['url'])
        elif el.name == 'drupal-entity':
            if el.has_attr('data-entity-embed-display'):
                if el['data-entity-embed-display'] == 'view_mode:node.related_content':
                    el.decompose()
                    continue
            logger.warning('unhandled drupal-entity in ' + item['url'])
        else:
            logger.warning('unhandled drupal element {} in {}'.format(el.name, item['url']))

    item['content_html'] = str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)


def test_handler():
    feeds = ['https://www.fiercevideo.com/rss/xml']
    for url in feeds:
        get_feed({"url": url}, True)
