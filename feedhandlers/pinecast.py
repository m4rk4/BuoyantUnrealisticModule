import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://pinecast.com/player/58386110-686c-46a9-9c54-c602170ce3d7?theme=minimal
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')

    item = {}
    item['title'] = soup.title.get_text()
    item['_audio'] = 'https://pinecast.com/listen/{}.mp3?source=embed&ext=asset.mp3'.format(paths[1])
    attachment = {}
    attachment['url'] = item['_audio']
    attachment['mime_type'] = 'audio/mpeg'
    item['attachments'] = []
    item['attachments'].append(attachment)

    duration = ''
    el = soup.find(class_='title-row')
    if el:
        matchobj = re.search(r'(\d+):(\d+):(\d+)', str(el))
        if matchobj:
            h = int(matchobj.group(1))
            m = int(matchobj.group(2))
            s = int(matchobj.group(3))
            d = []
            if h > 0:
                d.append('{} hr'.format(h))
            if m > 0:
                d.append('{} min'.format(m))
            if s > 0:
                d.append('{} s'.format(s))
            duration = '<br/><small>{}</small>'.format(', '.join(d))
    item['content_html'] = '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{}"><img src="{}/static/play_button-48x48.png"/></a><div style="padding-left:8px;"><b>{}</b>{}</div></div><div>&nbsp;</div>'.format(item['_audio'], config.server, item['title'], duration)

    return item
