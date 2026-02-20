import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from http.cookiejar import Cookie
from urllib.parse import parse_qs, quote_plus, urlsplit
from yt_dlp import YoutubeDL, DownloadError

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_author(info, ydl_opts):
    author = {}
    if info.get('uploader'):
        author = {
            "name": info['uploader']
        }

        if info.get('uploader_url'):
            author['url'] = info['uploader_url']
        elif info.get('channel_url'):
            author['url'] = info['channel_url']

        try:
            ydl_opts['playlist_items'] = '0'
            uploader_info = YoutubeDL(ydl_opts).extract_info(author['url'], download=False)
        except Exception as e:
            logger.warning('unexpected error occured getting uploader info for ' + author['url'])
            uploader_info = None

        if uploader_info:
            thumb = next((it for it in uploader_info['thumbnails'] if it['id'] == 'avatar_uncropped'), None)
            if thumb:
                author['avatar'] = config.server + '/image?url=' + quote_plus(thumb['url'])

        if 'avatar' not in author:
            page_html = utils.get_url_html(author['url'])
            if page_html:
                page_soup = BeautifulSoup(page_html, 'lxml')
                el = page_soup.find('meta', attrs={"property": "og:image"})
                if el:
                    author['avatar'] = config.server + '/image?url=' + quote_plus(el['content'])
    return author


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
            split_url = urlsplit('https://www.youtube.com/watch?v=' + video_id)
        elif 'embed' in paths and paths[1] != 'videoseries':
            video_id = paths[1]
        elif 'watch' in paths and query.get('v'):
            video_id = query['v'][0]
        elif 'shorts' in paths:
            video_id = paths[1]
        elif 'live' in paths:
            video_id = paths[1]
        if query.get('list'):
            playlist_id = query['list'][0]

    if False:
        page_html = utils.get_url_html('https://www.youtube-nocookie.com/embed/' + video_id, user_agent='googlebot-video')
        if page_html:
            m = re.search(r'ytcfg\.set\((.*?)\);window\.ytcfg', page_html)
            if m:
                ytcfg = json.loads(m.group(1))
                if save_debug:
                    utils.write_file(ytcfg, './debug/ytcfg.json')
                player_res = json.loads(ytcfg['PLAYER_VARS']['embedded_player_response'])
                if save_debug:
                    utils.write_file(player_res, './debug/player.json')
                item = {}
                item['id'] = video_id
                item['url'] = 'https://www.youtube.com/watch?v=' + video_id
                if player_res['previewPlayabilityStatus']['status'] == 'OK':
                    item['title'] = player_res['embedPreview']['thumbnailPreviewRenderer']['title']['runs'][0]['text']
                    item['image'] = player_res['embedPreview']['thumbnailPreviewRenderer']['defaultThumbnail']['thumbnails'][-1]['url']
                    item['author'] = {
                        "name": player_res['embedPreview']['thumbnailPreviewRenderer']['videoDetails']['embeddedPlayerOverlayVideoDetailsRenderer']['expandedRenderer']['embeddedPlayerOverlayVideoDetailsExpandedRenderer']['title']['runs'][0]['text'],
                        "url": "https://www.youtube.com" + player_res['embedPreview']['thumbnailPreviewRenderer']['videoDetails']['embeddedPlayerOverlayVideoDetailsRenderer']['channelThumbnailEndpoint']['channelThumbnailEndpoint']['urlEndpoint']['urlEndpoint']['url'],
                        "avatar": player_res['embedPreview']['thumbnailPreviewRenderer']['videoDetails']['embeddedPlayerOverlayVideoDetailsRenderer']['channelThumbnail']['thumbnails'][-1]['url']
                    }
                    heading = '<div style="height:32px; padding:8px; background-color:rgb(0,0,0,0.5);"><img src="{}" style="float:left; width:32px; height:32px; border-radius:50%;"><a href="{}" style="text-decoration:none;"><span style="line-height:32px; padding-left:8px; color:white; font-weight:bold;">{}</span></a></div>'.format(item['author']['avatar'], item['author']['url'], item['author']['name'])
                    caption = item['title'] + ' | <a href="' + item['url'] + '" target="_blank">Watch on YouTube</a>'
                    # video_url = 'https://www.youtube-nocookie.com/embed/' + video_id
                    video_url = config.server + '/video?url=' + quote_plus(item['url'])
                    item['content_html'] = utils.add_image(item['image'], caption, link=video_url, overlay=config.video_button_overlay, overlay_heading=heading)
                else:
                    item['image'] = 'https://i.ytimg.com/vi/' + video_id + '/maxresdefault.jpg'
                    caption = '<strong>' + player_res['previewPlayabilityStatus']['reason'] + '</strong> | <a href="' + item['url'] + '" target="_blank">Watch on YouTube</a>'
                    item['content_html'] = utils.add_image(item['image'], caption, link=item['url'], overlay=config.warning_overlay)
                return item

    # By default, the only combined video+audio format is 360p
    # player_client = mediaconnect has higher quality combined video+audio formats in m3u8 playlist
    ydl_opts = {
        "js_runtimes": {
            "deno": {
                "path": config.deno_exe
            }
        },
        "skip_download": True,
        "ignore_no_formats_error": True,
        "forcejson": True,
        "noprogress": True,
        "quiet": True,
        "extractor_args": {
        }
    }
    # if config.bgutil_base_url:
    #     ydl_opts['extractor_args']['youtubepot-bgutilhttp'] = {
    #         "base_url": [
    #             config.bgutil_base_url
    #         ]
    #     }
    # elif config.youtube_po_token:
    #     ydl_opts['extractor_args']['youtube']['po_token'] = [
    #         "mweb.gvs+" + config.youtube_po_token
    #     ]

    if 'player_client' in args:
        ydl_opts["extractor_args"]['youtube']['player_client'] = args['player_client'].split(',')

    if video_id:
        # TODO: capture warning info like "WARNING: [youtube] Video unavailable. The uploader has not made this video available in your country"
        # These are printed to stdout
        try:
            ydl = YoutubeDL(ydl_opts)
            if config.youtube_cookies:
                for key, val in config.youtube_cookies.items():
                    ydl.cookiejar.set_cookie(Cookie(
                        name=key, value=val, domain='.youtube.com', 
                        version=0, port=None, path='/', secure=True, expires=None, discard=False,
                        comment=None, comment_url=None, rest={'HttpOnly': None},
                        domain_initial_dot=True, port_specified=False, domain_specified=True, path_specified=False
                    ))
            video_info = ydl.extract_info('https://' + split_url.netloc + '/watch?v=' + video_id, download=False)
        except DownloadError as e:
            logger.warning(str(e))
            item = {}
            item['content_html'] = '<blockquote><strong><a href="https://' + split_url.netloc + '/watch?v={}" target="_blank">{}</a></strong></blockquote>'.format(video_id, str(e))
            return item

    if playlist_id and 'skip_playlist' not in args:
        # ydl_opts['playlist_items'] = '0-3'
        playlist_info = YoutubeDL(ydl_opts).extract_info('https://' + split_url.netloc + '/playlist?list=' + playlist_id, download=False)
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
    if video_id:
        item['id'] = video_info['id']
        # item['url'] = video_info['webpage_url']
        item['url'] = video_info['original_url']
        item['title'] = video_info['title']

        if video_info.get('timestamp'):
            dt_loc = datetime.fromtimestamp(video_info['timestamp'])
            tz_loc = pytz.timezone(config.local_tz)
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, date_only=True)

        # TODO: multiple creators: https://www.youtube.com/watch?v=lKWvtcGfLHI (how to get both creator ids?)
        item['author'] = get_author(video_info, ydl_opts)
        if 'name' not in item['author']:
            item['author']['name'] = 'Private uploader'
        if 'avatar' not in item['author']:
            item['author']['avatar'] = "data:image/svg+xml;utf8,<svg width='32' height='32' xmlns='http://www.w3.org/2000/svg'><circle r='16' cx='16' cy='16' fill='SlateGray'/></svg>"
        if 'url' in item['author']:
            heading = '<div style="height:32px; padding:8px; background-color:rgb(0,0,0,0.5);"><img src="' + item['author']['avatar'] + '" style="float:left; width:32px; height:32px; border-radius:50%;"><a href="' + item['author']['url'] + '" style="text-decoration:none;" target="_blank"><span style="line-height:32px; padding-left:8px; color:white; font-weight:bold;">' + item['author']['name'] + '</span></a></div>'
        else:
            heading = '<div style="height:32px; padding:8px; background-color:rgb(0,0,0,0.5);"><img src="' + item['author']['avatar'] + '" style="float:left; width:32px; height:32px; border-radius:50%;"><span style="line-height:32px; padding-left:8px; color:white; font-weight:bold;">' + item['author']['name'] + '</span></div>'

        item['tags'] = []
        if video_info.get('categories'):
            item['tags'] += video_info['categories'].copy()
        if video_info.get('tags'):
            item['tags'] += video_info['tags'].copy()

        item['image'] = video_info['thumbnail']

        audio = next((it for it in video_info['formats'] if it['format_id'] == '251'), None)
        if audio:
            item['_audio'] = audio['url']
            item['_audio_type'] = 'audio/ogg'
            attachment = {}
            attachment['url'] = item['_audio']
            attachment['mime_type'] = 'audio/ogg'
            item['attachments'] = []
            item['attachments'].append(attachment)

        # This is only streamable format
        video = next((it for it in video_info['formats'] if it['format_id'] == '18'), None)
        if video:
            item['_video'] = video['url']
            item['_video_type'] = 'video/mp4'

        if video_info.get('description'):
            item['summary'] = video_info['description']

        if video_info.get('duration_string'):
            item['_duration'] = video_info['duration_string']
        elif video_info.get('duration'):
            item['_duration'] = utils.calc_duration(video_info['duration'], time_format=':')
    else:
        item['id'] = playlist_info['id']
        item['url'] = playlist_info['original_url']
        item['title'] = playlist_info['title']

        if playlist_info.get('modified_date') and playlist_info['modified_date'].isnumeric():
            dt_loc = datetime(year=int(playlist_info['modified_date'][:4]), month=int(playlist_info['modified_date'][4:6]), day=int(playlist_info['modified_date'][6:8]))
            tz_loc = pytz.timezone(config.local_tz)
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, date_only=True)

        item['author'] = get_author(playlist_info, ydl_opts)
        if 'name' not in item['author']:
            item['author']['name'] = 'Private uploader'
        if 'avatar' not in item['author']:
            item['author']['avatar'] = "data:image/svg+xml;utf8,<svg width='32' height='32' xmlns='http://www.w3.org/2000/svg'><circle r='16' cx='16' cy='16' fill='SlateGray'/></svg>"
        if 'url' in item['author']:
            heading = '<div style="height:32px; padding:8px; background-color:rgb(0,0,0,0.5);"><img src="' + item['author']['avatar'] + '" style="float:left; width:32px; height:32px; border-radius:50%;"><a href="' + item['author']['url'] + '" style="text-decoration:none;" target="_blank"><span style="line-height:32px; padding-left:8px; color:white; font-weight:bold;">' + item['author']['name'] + '</span></a></div>'
        else:
            heading = '<div style="height:32px; padding:8px; background-color:rgb(0,0,0,0.5);"><img src="' + item['author']['avatar'] + '" style="float:left; width:32px; height:32px; border-radius:50%;"><span style="line-height:32px; padding-left:8px; color:white; font-weight:bold;">' + item['author']['name'] + '</span></div>'

        item['image'] = utils.closest_dict(playlist_info['thumbnails'], "width", 640)['url']

        if playlist_info.get('description'):
            item['summary'] = playlist_info['description']

    if playlist_info and playlist_info.get('entries'):
        item['_playlist'] = []
        for it in playlist_info['entries']:
            if it['availability'] == 'public':
                if it.get('artists'):
                    artist = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x for x in it['artists']]))
                elif it.get('uploader'):
                    artist = it['uploader']
                else:
                    artist = ''
                if artist == item['author']['name']:
                    artist = ''
                if split_url.netloc == 'music.youtube.com':
                    src = config.server + '/audio?url=' + quote_plus(it['original_url'])
                else:
                    src = config.server + '/video?url=' + quote_plus(it['original_url']) + '&novideojs'
                item['_playlist'].append({
                    "src": src,
                    "title": it['title'],
                    "artist": artist,
                    "image": it['thumbnail'],
                    "duration": it['duration_string'],
                    "url": it['original_url']
                })
        if len(item['_playlist']) == 0:
            del item['_playlist']

    if split_url.netloc == 'music.youtube.com':
        artist = ''
        if video_id:
            if video_info.get('artists'):
                artist = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(video_info['artists']))
        else:
            if playlist_info.get('artists'):
                artist = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(playlist_info['artists']))
        if not artist and item['author']['name'] == 'Private uploader':
            artist = '&nbsp;'
        item['content_html'] = utils.format_audio_content(item, logo=config.logo_youtubemusic, audio_src=config.server + '/audio?url=' + quote_plus(item['url']), author=artist)
        return item

    if '_playlist' in item:
        playlist_html = '<div style="margin:4px 0;"><a href="' + playlist_info['original_url'] + '" target="_blank"><b>Playlist:</b></a></div><div style="display:grid; grid-gap:1rem; grid-auto-flow:column; grid-auto-columns:150px; overflow-x:scroll; margin-bottom:1em;">'
        for it in item['_playlist']:
            playlist_html += '<figure style="margin:0; padding:0;"><a href="' + it['src'] + '" target="_blank"><img src="' + it['image'] + '" style="width:100%; aspect-ratio:16/9; object-fit:cover;" alt="' + it['title'] + '"></a><figcaption style="overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; line-clamp:2; -webkit-box-orient:vertical;" title="' + it['title'] + '"><a href="' + it['url'] + '" target="_blank"><small>' + it['title'] + '</small></a></figcaption></figure>'
        playlist_html += '</div>'
        fig_style = 'margin:1em 0 0 0; padding:0;'
    else:
        playlist_html = ''
        fig_style = 'margin:1em 0; padding:0;'

    if '_video' not in item and '_video_mp4' not in item:
        # https://www.youtube.com/watch?v=wKnOb6Z77ws
        caption = '<b>Video is unavailable:</b> ' + item['title'] + ' | <a href="' + item['url'] + '" target="_blank">Watch on YouTube</a>'
        if item['author']['name'] == 'Private uploader':
            poster = "data:image/svg+xml;utf8,<svg viewBox='0 0 64 36' xmlns='http://www.w3.org/2000/svg'><rect width='64' height='36' fill='rgb(204,204,204)'/></svg>"
            item['content_html'] = utils.add_image(poster, caption, link=item['url'], fig_style=fig_style, overlay=config.warning_overlay, overlay_heading=heading)
        else:
            item['content_html'] = utils.add_image(item['image'], caption, link=item['url'], fig_style=fig_style, overlay_heading=heading)
    else:
        caption = item['title'] + ' | <a href="' + item['url'] + '" target="_blank">Watch on YouTube</a>'
        video_url = config.server + '/video?url=' + quote_plus(item['url'])
        if 'player_client'  in args:
            video_url += '&player_client=' + args['player_client']
        item['content_html'] = utils.add_image(item['image'], caption, link=video_url, fig_style=fig_style, overlay=config.youtube_button_overlay, overlay_heading=heading)

    item['content_html'] += playlist_html

    if item.get('summary') and 'embed' not in args:
        summary_html = item['summary'].replace('\n', ' <br/> ')
        summary_html = re.sub(r'https?://([^\s]+)', r'<a href="\1">\1</a>', summary_html)
        item['content_html'] += '<p>{}</p>'.format(summary_html)

    return item
