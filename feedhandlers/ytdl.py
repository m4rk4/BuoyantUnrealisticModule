import pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from http.cookiejar import Cookie
from urllib.parse import parse_qs, quote_plus, urlsplit
from yt_dlp import YoutubeDL, DownloadError

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

    # By default, the only combined video+audio format is 360p
    # player_client = mediaconnect has higher quality combined video+audio formats in m3u8 playlist
    ydl_opts = {
        "skip_download": True,
        "ignore_no_formats_error": True,
        "forcejson": True,
        "noprogress": True,
        "quiet": True,
        "extractor_args": {
            "youtube": {
                "player_client": [
                    "web_safari"
                ],
                "po_token": [
                    "web_safari+" + config.youtube_po_token
                ]
            }
        }
    }

    if 'player_client' in args:
        ydl_opts["extractor_args"]['youtube']['player_client'] = args['player_client'].split(',')

    if video_id:
        # TODO: capture warning info like "WARNING: [youtube] Video unavailable. The uploader has not made this video available in your country"
        # These are printed to stdout
        try:
            ydl = YoutubeDL(ydl_opts)
            for key, val in config.youtube_cookies.items():
                ydl.cookiejar.set_cookie(Cookie(
                    name=key, value=val, domain='.youtube.com', 
                    version=0, port=None, path='/', secure=True, expires=None, discard=False,
                    comment=None, comment_url=None, rest={'HttpOnly': None},
                    domain_initial_dot=True, port_specified=False, domain_specified=True, path_specified=False
                ))
            video_info = ydl.extract_info('https://www.youtube.com/watch?v=' + video_id, download=False)
        except DownloadError as e:
            logger.warning(str(e))
            item = {}
            item['content_html'] = '<blockquote><strong><a href="https://www.youtube.com/watch?v={}" target="_blank">{}</a></strong></blockquote>'.format(video_id, str(e))
            return item
    if playlist_id and 'skip_playlist' not in args:
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

    if video_info.get('timestamp'):
        dt_loc = datetime.fromtimestamp(video_info['timestamp'])
        tz_loc = pytz.timezone(config.local_tz)
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    if video_info.get('uploader'):
        item['author'] = {
            "name": video_info['uploader']
        }
        ydl_opts['playlist_items'] = '0'
        if video_info.get('uploader_url'):
            item['author']['url'] = video_info['uploader_url']
        elif video_info.get('channel_url'):
            item['author']['url'] = video_info['channel_url']
        uploader_info =  YoutubeDL(ydl_opts).extract_info(item['author']['url'], download=False)
        if uploader_info:
            thumb = next((it for it in uploader_info['thumbnails'] if it['id'] == 'avatar_uncropped'), None)
            if thumb:
                item['author']['avatar'] = '{}/image?url={}&height=32&mask=ellipse'.format(config.server, quote_plus(thumb['url']))
        if 'avatar' not in item['author']:
            page_html = utils.get_url_html(item['author']['url'])
            if page_html:
                page_soup = BeautifulSoup(page_html, 'lxml')
                el = page_soup.find('meta', attrs={"property": "og:image"})
                if el:
                    item['author']['avatar'] = '{}/image?url={}&height=32&mask=ellipse'.format(config.server, quote_plus(el['content']))
        if 'avatar' not in item['author']:
            item['author']['avatar'] = '{}/image?width=32&height=32&mask=ellipse'.format(config.server)
        heading = '<table><tr><td style="width:32px; verticle-align:middle;"><img src="{}" /><td style="verticle-align:middle;"><a href="{}">{}</a></td></tr></table>'.format(item['author']['avatar'], item['author']['url'], item['author']['name'])
    else:
        item['author'] = {
            "name": "Private uploader",
            "avatar": '{}/image?width=32&height=32&mask=ellipse'.format(config.server)
        }
        heading = '<table><tr><td style="width:32px; verticle-align:middle;"><img src="{}" /><td style="verticle-align:middle;">{}</td></tr></table>'.format(item['author']['avatar'], item['author']['name'])

    item['tags'] = []
    if video_info.get('categories'):
        item['tags'] += video_info['categories'].copy()
    if video_info.get('tags'):
        item['tags'] += video_info['tags'].copy()

    item['image'] = video_info['thumbnail']

    audio = next((it for it in video_info['formats'] if it['format_id'] == '140'), None)
    if audio:
        item['_audio'] = audio['url']
        attachment = {}
        attachment['url'] = item['_audio']
        attachment['mime_type'] = 'audio/mp4'
        item['attachments'] = []
        item['attachments'].append(attachment)

    if 'format' in args:
        video = next((it for it in video_info['formats'] if it['format_id'] == args['format']), None)
    else:
        video = None
    if not video and 'manifest_url' in video_info:
        video = video_info
    else:
        # Default m3u8 formats:
        # Format 95 - 1280x720 m3u8
        # Format 94 - 854x480 m3u8
        # Format 96 - 1920x1080 m3u8
        for fmt in ['95', '94', '96']:
            video = next((it for it in video_info['formats'] if it['format_id'] == fmt), None)
            if video:
                break
    if video:
        if video['protocol'] == 'm3u8_native':
            item['_video'] = config.server + '/proxy/' + video['manifest_url']
            item['_video_type'] = 'application/x-mpegURL'
        else:
            item['_video'] = video['url']

    video = next((it for it in video_info['formats'] if it['format_id'] == '18'), None)
    if video:
        item['_video_mp4'] = video['url']

    # if video_info.get('url'):
    #     item['_video'] = video_info['url']
    #     if item['_video'].endswith('.m3u8'):
    #         item['_video_type'] = 'application/x-mpegURL'
    #         m3u8_playlist = utils.get_url_html(video_info['url'], headers=video_info['http_headers'])
    #         if m3u8_playlist:
    #             item['_m3u8'] = m3u8_playlist.replace('https://', config.server + '/proxy/https://')
    #             item['_video'] = config.server + '/proxy/' + item['url']
    #     elif video_info['video_ext'] == 'mp4':
    #         item['_video_type'] = 'video/mp4'
    #     elif video_info['video_ext'] == 'webm':
    #         item['_video_type'] = 'video/webm'

    if video_info.get('description'):
        item['summary'] = video_info['description']

    if '_video' not in item and '_video_mp4' not in item:
        if item['author']['name'] == 'Private uploader':
            poster = config.server + '/image?width=854&height=480&color=204,204,204&overlay=http%3A%2F%2Flocalhost:8080%2Fstatic%2Fyt_private_overlay.webp'
        else:
            poster = '{}/image?url={}&width=1000'.format(config.server, quote_plus(item['image']))
        caption = '<b>Video is unavailable:</b> {} | <a href="{}">Watch on YouTube</a>'.format(item['title'], item['url'])
        item['content_html'] = utils.add_image(poster, caption, link=item['url'], heading=heading)
    else:
        poster = '{}/image?url={}&width=1000&overlay=video'.format(config.server, quote_plus(item['image']))
        caption = '{} | <a href="{}">Watch on YouTube</a>'.format(item['title'], item['url'])
        video_url = config.server + '/video?url=' + quote_plus(item['url'])
        if 'player_client'  in args:
            video_url += '&player_client=' + args['player_client']
        item['content_html'] = utils.add_image(poster, caption, link=video_url, heading=heading)

    if playlist_info:
        item['_playlist'] = []
        item['content_html'] += '<h3>Playlist: <a href="{}/playlist?url={}">{}</a></h3>'.format(config.server, quote_plus(playlist_info['webpage_url']), playlist_info['title'])
        for video_info in playlist_info['entries']:
            if video_info['availability'] == 'public':
                item['_playlist'].append({
                    "src": config.server + '/video?url=' + quote_plus(video_info['webpage_url']) + '&novideojs',
                    "name": video_info['title'],
                    "artist": video_info['uploader'],
                    "image": video_info['thumbnail']
                })
                item['content_html'] += '<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:8px; margin:8px;">'
                video_url = config.server + '/video?url=' + quote_plus(video_info['webpage_url'])
                poster = '{}/image?url={}&width=640&overlay=video'.format(config.server, quote_plus(video_info['thumbnail']))
                item['content_html'] += '<div style="flex:1; min-width:128px; max-width:200px;"><a href="{}" target="_blank"><img src="{}" style="width:100%;"/></a></div>'.format(video_url, poster)
                item['content_html'] += '<div style="flex:2; min-width:256px;">'
                item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(video_info['webpage_url'], video_info['title'])
                if video_info.get('uploader_url'):
                    item['content_html'] += '<div style="margin:4px 0 4px 0;"><a href="{}">{}</a></div>'.format(video_info['uploader_url'], video_info['uploader'])
                elif video_info.get('channel_url'):
                    item['content_html'] += '<div style="margin:4px 0 4px 0;"><a href="{}">{}</a></div>'.format(video_info['channel_url'], video_info['uploader'])
                else:
                    item['content_html'] += '<div style="margin:4px 0 4px 0;">{}</div>'.format(video_info['uploader'])
                dt_loc = datetime.fromtimestamp(video_info['timestamp'])
                dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
                item['content_html'] += '<div style="font-size:0.9em;">{} &bull; {}</div>'.format(utils.format_display_date(dt, False), utils.calc_duration(video_info['duration']))
                item['content_html'] += '</div></div>'
            else:
                item['content_html'] += '<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:8px; margin:8px;">'
                video_url = video_info['webpage_url']
                poster = '{}/image?width=640&height=360&overlay=video'.format(config.server, quote_plus(video_info['thumbnail']))
                item['content_html'] += '<div style="flex:1; min-width:128px; max-width:200px;"><a href="{}" target="_blank"><img src="{}" style="width:100%;"/></a></div>'.format(video_url, poster)
                item['content_html'] += '<div style="flex:2; min-width:256px;">'
                item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;"><a href="{}">Video is unavailable</a></div>'.format(video_info['webpage_url'])
                item['content_html'] += '</div></div>'

        if playlist_info['playlist_count'] > len(playlist_info['entries']):
            item['content_html'] += '<p><a href="{}">View more on YouTube</a></p>'.format(playlist_info['webpage_url'])

    if item.get('summary') and 'embed' not in args:
        summary_html = item['summary'].replace('\n', ' <br/> ')
        summary_html = re.sub(r'https?://([^\s]+)', r'<a href="\1">\1</a>', summary_html)
        item['content_html'] += '<p>{}</p>'.format(summary_html)

    return item
