import pytz, re
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit
from yt_dlp import YoutubeDL

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    video_id = ''
    playlist_id = ''
    split_url = urlsplit(url)
    if not split_url.netloc and len(url) == 11:
        video_id = url
    else:
        paths = list(filter(None, split_url.path[1:].split('/')))
        query = parse_qs(split_url.query)
        if split_url.netloc == 'youtu.be':
            video_id = paths[0]
        elif 'embed' in paths and paths[1] != 'videoseries':
            video_id = paths[1]
        elif 'watch' in paths and query.get('v'):
            video_id = query['v'][0]
        elif 'shorts' in paths:
            video_id = paths[1]
        if query.get('list'):
            playlist_id = query['list'][0]

    ydl_opts = {
        "skip_download": True,
        "forcejson": True,
        "noprogress": True,
        "quiet": True
    }
    # By default, the only combined video+audio format is 360p
    # player_client = mediaconnect has higher quality combined video+audio formats in m3u8 playlist
    # TODO: This option gets higher quality formats in m3u8 they don't play due to 403 errors
    if 'player_client' in args:
        ydl_opts["extractor_args"] = {
            "youtube": {
                "player_client": args['player_client'].split(',')
            }
        }

    if video_id:
        video_info =  YoutubeDL(ydl_opts).extract_info('https://www.youtube.com/watch?v=' + video_id, download=False)
    if playlist_id:
        ydl_opts['playlist_items'] = '0-3'
        playlist_info = YoutubeDL(ydl_opts).extract_info('https://www.youtube.com/playlist?list=' + playlist_id, download=False)
        if playlist_info:
            if save_debug:
                utils.write_file(playlist_info, './debug/ytdl-playlist.json')
            if not video_id:
                video_info = playlist_info['entries'][0]
    else:
        playlist_info = None

    if not video_info:
        return None
    if save_debug:
        utils.write_file(video_info, './debug/ytdl.json')

    item = {}
    item['id'] = video_info['id']
    item['url'] = video_info['webpage_url']
    item['title'] = video_info['title']

    dt_loc = datetime.fromtimestamp(video_info['timestamp'])
    tz_loc = pytz.timezone(config.local_tz)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {
        "name": video_info['uploader']
    }
    ydl_opts['playlist_items'] = '0'
    uploader_info =  YoutubeDL(ydl_opts).extract_info(video_info['uploader_url'], download=False)
    if uploader_info:
        thumb = next((it for it in uploader_info['thumbnails'] if it['id'] == 'avatar_uncropped'), None)
        avatar = '{}/image?url={}&height=32&mask=ellipse'.format(config.server, quote_plus(thumb['url']))
    else:
        avatar = config.server + '/image?height=32&width=32&mask=ellipse'
    heading = '<table><tr><td style="width:32px; verticle-align:middle;"><img src="{}" /><td style="verticle-align:middle;"><a href="{}">{}</a></td></tr></table>'.format(avatar, video_info['uploader_url'], video_info['uploader'])

    item['tags'] = []
    if video_info.get('categories'):
        item['tags'] += video_info['categories'].copy()
    if video_info.get('tags'):
        item['tags'] += video_info['tags'].copy()

    item['_image'] = video_info['thumbnail']
    poster = '{}/image?url={}&width=1000&overlay=video'.format(config.server, quote_plus(item['_image']))

    audio = next((it for it in video_info['formats'] if it['format_id'] == '140'), None)
    if audio:
        item['_audio'] = audio['url']

    # if video_info.get('manifest_url'):
    #     item['_video'] = config.server + '/proxy/' + video_info['manifest_url']
    #     item['_video_type'] = 'application/x-mpegURL'
    if video_info.get('url'):
        item['_video'] = video_info['url']
        if item['_video'].endswith('.m3u8'):
            item['_video_type'] = 'application/x-mpegURL'
            m3u8_playlist = utils.get_url_html(video_info['url'], headers=video_info['http_headers'])
            if m3u8_playlist:
                item['_m3u8'] = m3u8_playlist.replace('https://', config.server + '/proxy/https://')
                item['_video'] = config.server + '/proxy/' + item['url']
        elif video_info['video_ext'] == 'mp4':
            item['_video_type'] = 'video/mp4'
        elif video_info['video_ext'] == 'webm':
            item['_video_type'] = 'video/webm'

    if video_info.get('description'):
        item['summary'] = video_info['description']

    caption = '{} | <a href="{}">Watch on YouTube</a>'.format(item['title'], item['url'])
    video_url = config.server + '/video?url=' + quote_plus(item['url'])
    if 'player_client'  in args:
        video_url += '&player_client=' + args['player_client']
    item['content_html'] = utils.add_image(poster, caption, link=video_url, heading=heading)

    if playlist_info:
        item['content_html'] += '<h3>Playlist: <a href="{}">{}</a></h3>'.format(playlist_info['webpage_url'], playlist_info['title'])
        for video_info in playlist_info['entries']:
            item['content_html'] += '<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:8px; margin:8px;">'
            video_url = config.server + '/video?url=' + quote_plus(video_info['webpage_url'])
            poster = '{}/image?url={}&width=640&overlay=video'.format(config.server, quote_plus(video_info['thumbnail']))
            item['content_html'] += '<div style="flex:1; min-width:128px; max-width:200px;"><a href="{}" target="_blank"><img src="{}" style="width:100%;"/></a></div>'.format(video_url, poster)
            item['content_html'] += '<div style="flex:2; min-width:256px;">'
            item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(video_info['webpage_url'], video_info['title'])
            item['content_html'] += '<div style="margin:4px 0 4px 0;"><a href="{}">{}</a></div>'.format(video_info['uploader_url'], video_info['uploader'])
            dt_loc = datetime.fromtimestamp(video_info['timestamp'])
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
            item['content_html'] += '<div style="font-size:0.9em;">{} &bull; {}</div>'.format(utils.format_display_date(dt, False), utils.calc_duration(video_info['duration']))
            item['content_html'] += '</div></div>'
        if playlist_info['playlist_count'] > len(playlist_info['entries']):
            item['content_html'] += '<p><a href="{}">View more on YouTube</a></p>'.format(playlist_info['webpage_url'])

    if item.get('summary') and 'embed' not in args:
        summary_html = item['summary'].replace('\n', ' <br/> ')
        summary_html = re.sub(r'https?://([^\s]+)', r'<a href="\1">\1</a>', summary_html)
        item['content_html'] += '<p>{}</p>'.format(summary_html)

    return item
