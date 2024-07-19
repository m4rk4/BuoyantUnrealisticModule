import math, re
from datetime import datetime
from urllib.parse import quote_plus

import config, utils

import logging
logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://play.libsyn.com/embed/episode/id/26304810/height/192/theme/modern/size/large/thumbnail/yes/custom-color/87A93A/time-start/00:00:00/playlist-height/200/direction/backward/download/yes
    m = re.search(r'\/episode\/id\/(\d+)', url)

    audio_json = utils.get_url_json('https://html5-player.libsyn.com/api/episode/id/{}'.format(m.group(1)))
    if not audio_json:
        return None
    if save_debug:
        utils.write_file(audio_json, './debug/audio.json')

    item = {}
    item['id'] = audio_json['_item']['item_id']
    item['url'] = audio_json['_item']['permalink_url']
    item['title'] = audio_json['_item']['item_title']

    dt = datetime.strptime(audio_json['release_date'], '%Y-%m-%d %H:%M:%S')
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, False)

    item['author'] = {}
    item['author']['name'] = audio_json['_item']['_show']['show_title']

    item['_image'] = 'https:' + audio_json['_item']['_image_url']

    item['_audio'] = audio_json['_item']['_primary_content']['_download_url']
    attachment = {}
    attachment['url'] = item['_audio']
    attachment['mime_type'] = 'audio/mpeg'
    item['attachments'] = []
    item['attachments'].append(attachment)

    item['summary'] = audio_json['_item']['item_body']

    duration = utils.calc_duration(float(audio_json['_item']['_primary_content']['duration']))
    videojs_src = '{}/videojs?src={}&type={}&poster={}'.format(config.server, quote_plus(item['_audio']), quote_plus('audio/mpeg'), quote_plus(item['_image']))
    poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))
    desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>{}<br/>{}&nbsp;&bull;&nbsp;{}</small>'.format(item['url'], item['title'], item['author']['name'], item['_display_date'], duration)

    item['content_html'] = '<table><tr><td style="width:128px;"><a href="{}"><img src="{}" style="width:100%;"/></a></td><td style="vertical-align:top;">{}</td></tr>'.format(videojs_src, poster, desc)
    if not 'embed' in args:
        item['content_html'] += '<tr><td colspan="2">{}</td></tr>'.format(item['summary'])
    item['content_html'] += '</table>'
    return item
