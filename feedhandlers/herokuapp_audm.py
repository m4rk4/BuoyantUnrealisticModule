from urllib.parse import parse_qs, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://audm.herokuapp.com/player-embed/?pub=atavist&articleID=titanic-of-pacific
    split_url = urlsplit(url)
    query = parse_qs(split_url.query)
    audm_json = utils.get_url_json('https://audm.herokuapp.com/player-embed/article/{}/{}'.format(query['pub'][0], query['articleID'][0]))
    if not audm_json:
        return None
    item = {}
    item['_audio'] = audm_json['audioUrl']
    attachment = {}
    attachment['url'] = item['_audio']
    attachment['mime_type'] = 'audio/mpeg'
    item['attachments'] = []
    item['attachments'].append(attachment)
    item['content_html'] = '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">Listen to article</a></span></div>'.format(item['_audio'], config.server)
    return item
