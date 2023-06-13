import math, random
from datetime import datetime
from urllib.parse import quote_plus

import config, utils
from feedhandlers import rss, youtube

import logging
logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # Seems like instances are rate limited, so choose one at random
    # https://github.com/TeamPiped/Piped/wiki/Instances
    piped_instances = [
        "https://pipedapi.kavin.rocks/",
        "https://pipedapi.tokhmi.xyz/"
        "https://api-piped.mha.fi/",
        "https://piped-api.hostux.net/",
        "https://pipedapi-libre.kavin.rocks/",
        "https://pipedapi.leptons.xyz/",
    ]

    yt_video_id, yt_list_id = utils.get_youtube_id(url)
    if not yt_video_id and not yt_list_id:
        return None

    if yt_list_id:
        for piped_instance in piped_instances:
            piped_json = utils.get_url_json('{}playlists/{}'.format(piped_instance, yt_list_id), user_agent='googlebot', retries=1)
            if piped_json:
                break
        if not piped_json:
            return None
        if save_debug:
            utils.write_file(piped_json, './debug/youtube.json')

        if yt_video_id:
            item = get_content('https://piped.video/watch?v={}'.format(yt_video_id), args, site_json, False)
            item['url'] = 'https://piped.video/watch?v={}&list={}'.format(yt_video_id, yt_list_id)
        else:
            item = get_content('https://piped.video' + piped_json['relatedStreams'][0]['url'], args, site_json, False)
            item['id'] = yt_list_id
            item['url'] = 'https://piped.video/playlist?list={}'.format(yt_list_id)
            item['title'] = piped_json['name']
            # TODO: clean attachments
            item['content_html'] = ''
        item['content_html'] += '<h3>Playlist</h3>'
        for i, it in enumerate(piped_json['relatedStreams']):
            if 'embed' in args and i > 2:
                break
            s = float(it['duration'])
            h = math.floor(s / 3600)
            s = s - h * 3600
            m = math.floor(s / 60)
            s = s - m * 60
            if h > 0:
                duration = '{:0.0f}:{:02.0f}:{:02.0f}'.format(h, m, s)
            else:
                duration = '{:0.0f}:{:02.0f}'.format(m, s)
            dt = datetime.fromtimestamp(it['uploaded'] / 1000)
            if 'audio' in args:
                play_url = '{}/audio?url={}'.format(config.server, quote_plus('https://www.youtube.com' + it['url']))
                poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(it['thumbnail']))
            else:
                play_url = '{}/video?url={}'.format(config.server, quote_plus('https://www.youtube.com' + it['url']))
                poster = '{}/image?height=128&url={}&overlay=video'.format(config.server, quote_plus(it['thumbnail']))
            desc = '<div style="font-size:1.1em; font-weight:bold;"><a href="https://piped.video{}">{}</a></div><div><a href="https://piped.video{}">{}</a></div><div><small>{}&nbsp;&bull;&nbsp;Uploaded {}</small></div>'.format(it['url'], it['title'], it['uploaderUrl'], it['uploaderName'], duration, utils.format_display_date(dt, False))
            item['content_html'] += '<table><tr><td style="width:128px;"><a href="{}"><img src="{}" style="width:100%;"/></a></td><td style="vertical-align:top;">{}</td></tr></table><div>&nbsp;</div>'.format(play_url, poster, desc)
    else:
        for piped_instance in piped_instances:
            piped_json = utils.get_url_json('{}streams/{}'.format(piped_instance, yt_video_id), user_agent='googlebot', retries=2)
            if piped_json:
                break
        if not piped_json:
            return None
        if save_debug:
            utils.write_file(piped_json, './debug/youtube.json')

        item = {}
        item['id'] = yt_video_id

        if piped_json.get('error'):
            item['url'] = 'https://www.youtube.com/watch?v={}'.format(yt_video_id)
            item['title'] = piped_json['message']
            poster = '{}/image?width=1280&height=720&overlay={}'.format(config.server, quote_plus('https://s.ytimg.com/yts/img/meh7-vflGevej7.png'))
            item['content_html'] = utils.add_image(poster, piped_json['message'], link=item['url'])
            return item

        item['url'] = 'https://piped.video/watch?v={}'.format(yt_video_id)
        item['title'] = piped_json['title']

        # TODO: timezone?
        dt = datetime.fromisoformat(piped_json['uploadDate'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, False)

        item['author'] = {"name": piped_json['uploader']}

        if piped_json.get('category'):
            item['tags'] = []
            item['tags'].append(piped_json['category'])

        item['_image'] = piped_json['thumbnailUrl']

        if piped_json.get('description'):
            item['summary'] = piped_json['description']

        audio_stream = None
        video_stream = None
        item['attachments'] = []
        if piped_json.get('audioStreams'):
            audio_stream = next((it for it in piped_json['audioStreams'] if (it['format'] == 'M4A' and it['bitrate'] > 120000)), None)
            if audio_stream:
                item['_audio'] = audio_stream['url']
                attachment = {}
                attachment['url'] = audio_stream['url']
                attachment['mime_type'] = audio_stream['mimeType']
                item['attachments'].append(attachment)

        if piped_json.get('videoStreams'):
            video_stream = next((it for it in piped_json['videoStreams'] if (it['format'] == 'MPEG_4' and it['quality'] == '720p' and it['videoOnly'] == False)), None)
            if video_stream:
                item['_video'] = video_stream['url']
                attachment = {}
                attachment['url'] = video_stream['url']
                attachment['mime_type'] = video_stream['mimeType']
                item['attachments'].append(attachment)
        if not video_stream and piped_json.get('hls'):
            item['_video'] = piped_json['hls']
            video_stream = {}
            video_stream['url'] = piped_json['hls']
            video_stream['mimeType'] = 'application/x-mpegURL'

        if audio_stream and 'audio' in args:
            s = float(piped_json['duration'])
            h = math.floor(s / 3600)
            s = s - h * 3600
            m = math.floor(s / 60)
            s = s - m * 60
            if h > 0:
                duration = '{:0.0f}:{:02.0f}:{:02.0f}'.format(h, m, s)
            else:
                duration = '{:0.0f}:{:02.0f}'.format(m, s)
            play_url = '{}/audio?url={}'.format(config.server, quote_plus('https://www.youtube.com/watch?v=' + item['id']))
            poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))
            desc = '<div style="font-size:1.1em; font-weight:bold;"><a href="https://piped.video{}">{}</a></div><div><a href="https://piped.video{}">{}</a></div><div><small>{}&nbsp;&bull;&nbsp; Uploaded {}</small></div>'.format(item['url'], item['title'], piped_json['uploaderUrl'], piped_json['uploader'], duration, item['_display_date'])
            item['content_html'] = '<table><tr><td style="width:128px;"><a href="{}"><img src="{}" style="width:100%;"/></a></td><td style="vertical-align:top;">{}</td></tr></table><div>&nbsp;</div>'.format(play_url, poster, desc)
        elif video_stream:
            if piped_json.get('uploaderAvatar'):
                avatar = '{}/image?url={}&height=32&mask=ellipse'.format(config.server, quote_plus(piped_json['uploaderAvatar']))
            else:
                avatar = '{}/image?height=32&width=32&mask=ellipse'.format(config.server)
            #heading = '<div style="display:flex; align-items:center; margin:8px; gap:8px;"><img src="{}"/><div style="font-weight:bold;"><a href="https://piped.video{}">{}</div></div>'.format(avatar, piped_json['uploaderUrl'], piped_json['uploader'])
            heading = '<table><tr><td style="verticle-align:middle;"><img src="{}" /><td style="verticle-align:middle;"><a href="{}">{}</a></td></tr></table>'.format(avatar, piped_json['uploaderUrl'], piped_json['uploader'])
            caption = '<a href="https://piped.video/watch?v={0}">{1}</a> | <a href="https://piped.video/embed/{0}">Watch on Piped</a> | <a href="https://www.youtube-nocookie.com/embed/{0}">Watch on YouTube</a>'.format(item['id'], item['title'])
            play_url = '{}/video?url={}'.format(config.server, quote_plus('https://www.youtube.com/watch?v=' + item['id']))
            item['content_html'] = utils.add_video(play_url, video_stream['mimeType'], item['_image'], caption, heading=heading)
        if item.get('summary') and 'embed' not in args:
            item['content_html'] += utils.add_blockquote(item['summary'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
