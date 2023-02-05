import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import config, utils
from feedhandlers import rss, substack, wp, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))

    if paths[0] == 'p':
        return substack.get_content(url, args, site_json, save_debug)
    elif paths[0] == 'podcast-episode':
        if args.get('add_subtitle'):
            del args['add_subtitle']
        item = wp.get_content(url, args, site_json, save_debug)
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find(class_='podcast-player-section')
        if el:
            it = el.find('iframe')
            if it:
                item['content_html'] += utils.add_embed(it['src'])
        el = soup.find('div', class_='the-content')
        if el:
            item['content_html'] += '<hr/><h3>Episode Notes</h3>' + el.decode_contents()
        el = soup.find('ul', class_='transcript-blocks')
        if el:
            item['content_html'] += '<hr/><h3>Transcript</h3><table style="width:100%;">'
            for it in el.find_all('li'):
                item['content_html'] += '<tr><td style="vertical-align:top; width:6em;">'
                elm = it.find(class_='transcript-block__speaker')
                item['content_html'] += '<b>{}</b>'.format(elm.get_text())
                elm = it.find(class_='transcript-block__timestamp')
                item['content_html'] += '<br/>{}</td>'.format(elm.get_text())
                elm = it.find(class_='transcript-block__body')
                item['content_html'] += '<td style="vertical-align:top;">{}<br/><br/></td></tr>'.format(elm.decode_contents())
            item['content_html'] += '</table>'
        return item
    else:
        return wp_posts.get_content(url, args, site_json, save_debug)

def get_feed(url, args, site_json, save_debug=False):
    # TODO: substack feed
    return rss.get_feed(url, args, site_json, save_debug, get_content)
