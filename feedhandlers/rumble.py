import cloudscraper, json, re
from datetime import datetime, timezone
from urllib.parse import quote_plus, unquote, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    embed_url = ''
    if 'embed' in paths:
        embed_url = url
        video_id = paths[1]
    else:
        oembed_json = utils.get_url_json('https://rumble.com/api/Media/oembed.json?url=' + quote_plus(url))
        if oembed_json:
            m = re.search(r'https://rumble\.com/embed/[^"]+', oembed_json['html'])
            if m:
                embed_url = m.group(0)
                paths = list(filter(None, urlsplit(embed_url).path[1:].split('/')))
                video_id = paths[1]
    if not embed_url:
        logger.warning('unhandled url ' + url)
        return None

    page_html = utils.get_url_html(embed_url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    m = re.search(r'\["{}"\]=({{.*?}});\w'.format(paths[1]), page_html)
    if not m:
        logger.warning('unable to parse rumble player data in ' + url)
        return None

    player_data = re.sub(r',loaded:[^},]+', '', m.group(1))
    player_json = json.loads(player_data)
    if save_debug:
        utils.write_file(player_json, './debug/debug.json')

    item = {}
    item['id'] = video_id
    item['url'] = 'https://rumble.com' + player_json['l']
    item['title'] = player_json['title']

    dt = datetime.fromisoformat(player_json['pubDate']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": player_json['author']['name']}

    item['_image'] = player_json['i']
    item['_video'] = player_json['u']['mp4']['url']
    if 'embed' not in args:
        caption = '{} | <a href="{}">Watch on Rumble</a>'.format(item['title'], item['url'])
    else:
        caption = ''
    item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['_image'], caption)
    return item