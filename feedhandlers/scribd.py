import json
from bs4 import BeautifulSoup
from urllib.parse import urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://www.scribd.com/embeds/595926714/content?start_page=1&view_mode=scroll&access_key=key-YsE0rA9wCDdh6vL0OukK
    # https://www.scribd.com/document/646431800/Sex-Racism-Corruption-Documents-Detail-Widespread-Misconduct-in-US-Marshals
    item = {}
    image = ''
    scribd_json = None

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    doc_id = paths[1]
    page_url = 'https://www.scribd.com/document/{}'.format(doc_id)
    page_html = utils.get_url_html(page_url)
    if page_html:
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', attrs={"type": "application/json", "data-hypernova-id": True})
        if el:
            scribd_json = json.loads(el.string[el.string.find('{'):el.string.rfind('}')+1])
            if save_debug:
                utils.write_file(scribd_json, './debug/scribd.json')
            item['id'] = scribd_json['body_props']['document']['id']
            item['url'] = scribd_json['body_props']['sharing_buttons_props']['url']
            item['title'] = scribd_json['body_props']['document']['title']
            item['author'] = {"name": scribd_json['body_props']['document']['publisher_info']['name']}
            item['_image'] = scribd_json['body_props']['sharing_buttons_props']['thumbnail_url']
            if scribd_json['body_props']['document'].get('description'):
                item['summary'] = scribd_json['body_props']['document']['description']
            content_url = item['url']
        else:
            el = soup.find('meta', attrs={"property": "og:image"})
            if el:
                image = el['content']

    embed_props = utils.get_url_json('https://www.scribd.com/doc-page/embed-modal-props/{}'.format(doc_id))
    if embed_props:
        if not item:
            item['id'] = embed_props['document_id']
            item['url'] = embed_props['embed_path']
            item['title'] = embed_props['title']
            item['author'] = {"name": embed_props['user']['name']}
        content_url = '{}?start_page=1&view_mode=scroll&access_key={}'.format(embed_props['embed_path'], embed_props['access_key'])

    if not item.get('_image') and image:
        item['_image'] = image

    if item.get('_image'):
        caption = '<a href="{}">{}</a> (www.scribd.com)'.format(item['url'], item['title'])
        if item.get('summary'):
            caption += ' | ' + item['summary']
        item['content_html'] = utils.add_image(item['_image'], caption)
    else:
        poster = '{}/image?width=128&height=160'.format(config.server)
        item['content_html'] = '<table><tr><td style="width:128px;"><a href="{}"><img src="{}" style="width:100%;" /></a></td><td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(content_url, poster, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<div>{}</div>'.format(item['summary'])
            item['content_html'] += '<div style="font-size:0.8em;">www.scribd.com</div>'
        item['content_html'] += '</td></tr></table>'
    return item
