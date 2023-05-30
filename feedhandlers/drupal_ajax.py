import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    #drupal_ajax = utils.get_url_json(utils.clean_url(url) + '?_wrapper_format=drupal_ajax')
    drupal_html = utils.get_url_html(utils.clean_url(url) + '?_wrapper_format=drupal_ajax')
    if not drupal_html:
        return None
    if save_debug:
        utils.write_file(drupal_html, './debug/debug.html')

    drupal_ajax = json.loads(re.sub(r'^<textarea>(.*)</textarea>$', r'\1', drupal_html))
    if save_debug:
        utils.write_file(drupal_ajax, './debug/debug.json')

    soup = None
    content = None
    for it in drupal_ajax:
        if it.get('command') and it['command'] == 'insert':
            soup = BeautifulSoup(it['data'], 'html.parser')
            content = soup.find(class_=['content', 'field--name-body'])
            if content:
                break
    if not content:
        return None

    item = {}
    if content:
        for el in content.find_all(class_=['cdw-related-content', 'disqus_thread', 'share-buttons-h', 'Subtopics']):
            el.decompose()

        for el in content.find_all(id='disqus_thread'):
            el.decompose()

        item['content_html'] = content.decode_contents()
    return item
