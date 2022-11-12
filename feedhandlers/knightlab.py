import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    # https://cdn.knightlab.com/libs/juxtapose/latest/embed/index.html?uid=322232da-3859-11ed-b5bc-6595d9b17862
    # Embeds only
    if '/juxtapose/' not in url:
        logger.warning('unhanlded url ' + url)
        return None
    split_url = urlsplit(url)
    query = parse_qs(split_url.query)
    if not query.get('uid'):
        logger.warning('unhanlded url ' + url)
        return None

    jux_json = utils.get_url_json('https://s3.amazonaws.com/uploads.knightlab.com/juxtapose/{}.json'.format(query['uid'][0]))
    if not jux_json:
        return None
    if save_debug:
        utils.write_file(jux_json, './debug/juxtapose.json')

    item = {}
    item['content_html'] = '<table style="width:100%;"><tr>'
    for image in jux_json['images']:
        captions = []
        if image.get('label'):
            captions.append(image['label'])
        if image.get('credit'):
            captions.append(image['credit'])
        item['content_html'] += '<th>{}</th>'.format(' | '.join(captions))
    item['content_html'] += '</tr><tr>'
    for image in jux_json['images']:
        item['content_html'] += '<td style="padding:0;"><img src="{}" style="width:100%"/></td>'.format(image['src'])
    item['content_html'] += '</tr><tr><td colspan="{}" style="padding:0;"><small><a href="{}">View juxtapose embed</a></small></td></tr></table>'.format(len(jux_json['images']), url)
    return item
