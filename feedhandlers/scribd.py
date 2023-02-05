import json, re

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://www.scribd.com/embeds/595926714/content?start_page=1&view_mode=scroll&access_key=key-YsE0rA9wCDdh6vL0OukK
    if '/embeds/' not in url:
        logger.warning('unhandled url ' + url)
        return None
    page_html = utils.get_url_html(url)
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')
    m = re.search(r'EmbedsShow\([^\{]+(\{.*\})\);\n', page_html)
    if not m:
        logger.warning('unable to find EmbedsShow data in ' + url)
        return None

    embed_json = json.loads(m.group(1))
    if save_debug:
        utils.write_file(embed_json, './debug/debug.json')

    item = {}
    item['id'] = embed_json['toolbar']['share_opts']['id']
    item['url'] = embed_json['toolbar']['share_opts']['url']
    item['title'] = embed_json['toolbar']['share_opts']['title']
    item['_image'] = embed_json['toolbar']['share_opts']['thumbnail_url']
    item['summary'] = embed_json['toolbar']['share_opts']['description']
    caption = '{} | <a href="{}"><b>View document</b></a>'.format(item['title'], item['url'])
    item['content_html'] = utils.add_image(item['_image'], caption, link=item['url'] )
    return item
