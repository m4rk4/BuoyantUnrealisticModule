import certifi, json, re
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_cffi_requests
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug):
    split_url = urlsplit(url)
    if split_url.path.startswith('/video'):
        vimeo_id = split_url.path.split('/')[2]
    else:
        vimeo_id = split_url.path.split('/')[1]

    if not vimeo_id.isnumeric():
        logger.warning('unable to determine Vimeo id in ' + url)
        return None

    player_url = 'https://player.vimeo.com/video/{}'.format(vimeo_id)
    # vimeo_html = utils.get_url_html(player_url, 'desktop')
    # if not vimeo_html:
    #     return None
    r = curl_cffi_requests.get(player_url, impersonate="chrome")
    if r.status_code != 200:
        logger.warning('curl_cffi requests error {} getting {}'.format(r.status_code, player_url))
        return None
    vimeo_html = r.text

    soup = BeautifulSoup(vimeo_html, 'lxml')
    el = soup.find('script', string=re.compile(r'window\.playerConfig'))
    if not el:
        logger.warning('unable to parse playerConfig in ' + player_url)
        return None

    vimeo_json = None
    i = el.string.find('{')
    try:
        vimeo_json = json.loads(el.string[i:])
    except:
        m = re.search(r'^({.*?});?\s+var', el.string[i:])
        if m:
            vimeo_json = json.loads(m.group(1))
    if not vimeo_json:
        if save_debug:
            utils.write_file(el.string, './debug/vimeo.txt')
        logger.warning('error converting playerConfig to json in ' + player_url)
        return None

    if save_debug:
        utils.write_file(vimeo_json, './debug/vimeo.json')

    item = {}
    item['id'] = vimeo_id
    item['url'] = vimeo_json['video']['share_url']
    item['title'] = vimeo_json['video']['title']

    if vimeo_json.get('seo') and vimeo_json['seo'].get('upload_date'):
        dt = datetime.strptime(vimeo_json['seo']['upload_date'], '%Y-%m-%d %H:%M:%S').astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {}
    item['author']['name'] = vimeo_json['video']['owner']['name']
    item['authors'] = []
    item['authors'].append(item['author'])

    if vimeo_json['video'].get('thumbnail_url'):
        item['image'] = vimeo_json['video']['thumbnail_url']
    elif vimeo_json['video'].get('thumbs') and vimeo_json['video']['thumbs'].get('base'):
        item['image'] = vimeo_json['video']['thumbs']['base'] + '_1000'

    if not vimeo_json['video'].get('live_event'):
        if vimeo_json['request']['files'].get('hls'):
            for key, val in vimeo_json['request']['files']['hls']['cdns'].items():
                video = val
                video_type = 'application/x-mpegURL'
                break
        elif vimeo_json['request']['files'].get('progressive'):
            video = utils.closest_dict(vimeo_json['request']['files']['progressive'], 'width', 640)
            video_type = 'video/mp4'
        item['_video'] = video['url']
        caption = '{} | <a href="{}">Watch on Vimeo</a>'.format(item['title'], player_url)
        if args and args.get('embed'):
            video_src = '{}/video?url={}'.format(config.server, quote_plus(item['url']))
            poster = '{}/image?url={}&width=1080&overlay=video'.format(config.server, quote_plus(item['image']))
            item['content_html'] = utils.add_image(poster, caption, link=video_src)
        else:
            item['content_html'] = utils.add_video(video['url'], video_type, item['image'], caption)
    else:
        poster = '{}/image?url={}&overlay=video'.format(config.server, quote_plus(item['image']))
        item['content_html'] = utils.add_image(poster, 'Live event: {}'.format(item['title']), link=item['url'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
