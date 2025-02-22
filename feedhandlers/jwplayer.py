import re
from datetime import datetime, timezone

import utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # https://cdn.jwplayer.com/players/QjZKj8Po-AjIcq1uW.js
    # https://content.jwplatform.com/players/K1j14B6g.html
    # https://cdn.jwplayer.com/manifests/uqYcHzXZ.m3u8
    # https://cdn.jwplayer.com/videos/q6Eqk0Xt-4VHSaSK0.mp4
    m = re.search(r'/(players|previews|v2/media|manifests|videos)/([^-\.]+)', url)
    if not m:
        logger.warning('unhandled content url ' + url)
        return None

    video_json = utils.get_url_json('https://cdn.jwplayer.com/v2/media/' + m.group(2))
    if not video_json:
        video_json = utils.get_url_json('https://cdn.jwplayer.com/v2/playlists/' + m.group(2))
        if not video_json:
            return None
    if save_debug:
        utils.write_file(video_json, './debug/video.json')

    return get_video_content(video_json['playlist'][0], args)


def get_video_content(video_json, args):
    item = {}
    item['id'] = video_json['mediaid']
    item['url'] = video_json['link']
    item['title'] = video_json['title']

    dt = datetime.fromtimestamp(video_json['pubdate']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    if video_json.get('owner'):
        item['author'] = {
            "name": video_json['owner']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

    if video_json.get('tags'):
        item['tags'] = video_json['tags'].split(',')

    image = utils.closest_dict(video_json['images'], 'width', 1080)
    item['image'] = image['src']
    item['_image'] = image['src']

    video_src = next((it for it in video_json['sources'] if it['type'] == 'application/vnd.apple.mpegurl'), None)
    if video_src:
        item['_video'] = video_src['file']
        item['_video_type'] = video_src['type']

    videos_mp4 = [x for x in video_json['sources'] if x.get('type') == 'video/mp4']
    if len(videos_mp4) > 0:
        if len(videos_mp4) == 1:
            video_src = videos_mp4[0]
        else:
            video_src = utils.closest_dict(videos_mp4, 'height', 720)
        if '_video' not in item:
            item['_video'] = video_src['file']
            item['_video_type'] = video_src['type']
        else:
            item['_video_mp4'] = video_src['file']

    if '_video' not in item:
        video_src = video_json['sources'][0]
        item['_video'] = video_src['file']
        item['_video_type'] = video_src['type']

    if video_json.get('description'):
        item['summary'] = video_json['description']

    item['content_html'] = utils.add_video(item['_video'], item['_video_type'], item['image'], 'Watch: ' + item['title'], use_videojs=True)

    if 'embed' not in args and 'summary' in item:
        item['content_html'] += '<p>' + item['summary'] + '</p>'
    return item


def get_feed(url, args, site_json, save_debug=False):
    # Playlist urls only: https://cdn.jwplayer.com/v2/playlists/oLRZ3mum
    m = re.search(r'/playlists/([^-\.]+)', url)
    if not m:
        logger.warning('unhandled feed url ' + url)
        return None

    playlist_json = utils.get_url_json('https://cdn.jwplayer.com/v2/playlists/' + m.group(1))
    if not playlist_json:
        return None
    if save_debug:
        utils.write_file(playlist_json, './debug/feed.json')

    n = 0
    feed_items = []
    for video in playlist_json['playlist']:
        video_url = 'https://cdn.jwplayer.com/v2/media/' + video['mediaid']
        item = get_video_content(video, args)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    if playlist_json.get('description'):
        feed['title'] = playlist_json['description']
    elif playlist_json.get('title'):
        feed['title'] = playlist_json['title']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
