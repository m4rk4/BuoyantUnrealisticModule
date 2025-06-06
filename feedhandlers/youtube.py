import json, math, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from pytube.cipher import Cipher
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def search(query, save_debug=False):
    search_html = utils.get_url_html(
        'https://www.youtube.com/results?search_query=' + quote_plus(query))
    if search_html:
        m = re.search(r'var ytInitialData = (.*});<\/script>', search_html)
        if m:
            search_json = json.loads(m.group(1))
            if save_debug:
                utils.write_file(search_json, './debug/search.json')
            contents = \
            search_json['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer'][
                'contents'][0]['itemSectionRenderer']['contents']
            for content in contents:
                if content.get('videoRenderer'):
                    return content['videoRenderer']['videoId']
    logger.warning('unable to get Youtube search results for query "{}"'.format(query))
    return ''


def get_playlist_info(playlist_id):
    # https://github.com/user234683/youtube-local/blob/master/youtube/playlist.py
    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Linux; Android 7.0; Redmi Note 4 Build/NRD90M) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Mobile Safari/537.36",
        "X-YouTube-Client-Name": "2",
        "X-YouTube-Client-Version": "2.20180614"
    }
    return utils.get_url_json('https://m.youtube.com/playlist?list={}&pbj=1'.format(playlist_id), headers=headers)


def get_author_info(channel_id):
    author = None
    # https://github.com/user234683/youtube-local/blob/master/youtube/channel.py
    headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Linux; Android 7.0; Redmi Note 4 Build/NRD90M) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Mobile Safari/537.36",
        "X-YouTube-Client-Name": "2",
        "X-YouTube-Client-Version": "2.20180614"
    }
    channel_url = 'https://m.youtube.com/channel/{}/about?pbj=1'.format(channel_id)
    #print(channel_url)
    channel_json = utils.get_url_json(channel_url, headers=headers)
    if channel_json:
        # utils.write_file(channel_json, './debug/channel.json')
        if isinstance(channel_json, list):
            channel_response = next((it for it in channel_json if it.get('response')), None)
        elif isinstance(channel_json, dict) and channel_json.get('response'):
            channel_response = channel_json
        if channel_response and channel_response['response'].get('metadata'):
            author = {}
            author['name'] = channel_response['response']['metadata']['channelMetadataRenderer']['title']
            author['url'] = channel_response['response']['metadata']['channelMetadataRenderer']['vanityChannelUrl']
            author['avatar'] = '{}/image?url={}&height=32&mask=ellipse'.format(config.server, quote_plus(channel_response['response']['metadata']['channelMetadataRenderer']['avatar']['thumbnails'][0]['url']))
    return author


def get_player_response(video_id):
    player_response = None
    player_url = ''
    page_html = utils.get_url_html('https://www.youtube.com/watch?v={}'.format(video_id))
    #utils.write_file(page_html, './debug/youtube.html')
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', string=re.compile(r'var ytInitialPlayerResponse\s?='))
    if el:
        i = el.string.find('{')
        j = el.string.rfind('}') + 1
        player_response = json.loads(el.string[i:j])
    m = re.search(r'"(?:PLAYER_JS_URL|jsUrl)"\s*:\s*"([^"]+)"', page_html)
    if m:
        player_url = 'https://www.youtube.com' + m.group(1)
    return player_response, player_url


def format_duration(seconds):
    s = float(seconds)
    h = math.floor(s / 3600)
    s = s - h * 3600
    m = math.floor(s / 60)
    s = s - m * 60
    if h > 0:
        duration = '{:0.0f}:{:02.0f}:{:02.0f}'.format(h, m, s)
    else:
        duration = '{:0.0f}:{:02.0f}'.format(m, s)
    return duration


def get_content(url, args, site_json, save_debug=False):
    #video_id, playlist_id = utils.get_youtube_id(url)
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

    video_list = None
    item = {}
    if video_id:
        item['id'] = video_id
        item['url'] = 'https://www.youtube.com/watch?v=' + video_id

        player_response, player_url = get_player_response(video_id)
        if not player_response:
            return None
        if save_debug:
            utils.write_file(player_response, './debug/youtube.json')
        if not player_response.get('videoDetails'):
            if player_response['playabilityStatus'].get('errorScreen') and player_response['playabilityStatus']['errorScreen'].get('playerErrorMessageRenderer'):
                reasons = []
                if player_response['playabilityStatus']['errorScreen']['playerErrorMessageRenderer'].get('reason'):
                    msg = player_response['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['reason']['simpleText']
                    if not msg.endswith('.'):
                        msg += '.'
                    reasons.append(msg)
                if player_response['playabilityStatus']['errorScreen']['playerErrorMessageRenderer'].get('subreason'):
                    if player_response['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['subreason'].get('simpleText'):
                        msg = player_response['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['subreason']['simpleText']
                        if not msg.endswith('.'):
                            msg += '.'
                        reasons.append(msg)
                    elif player_response['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['subreason'].get('runs'):
                        for it in player_response['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['subreason']['runs']:
                            msg = it['text']
                            if not msg.endswith('.'):
                                msg += '.'
                            reasons.append(msg)
                if reasons:
                    item['title'] = ' '.join(reasons)
            if not item.get('title'):
                item['title'] = player_response['playabilityStatus']['status']
            caption = '<strong>{}</strong> | <a href="{}">Watch on YouTube</a>'.format(item['title'], item['url'])
            if player_response['playabilityStatus']['errorScreen']['playerErrorMessageRenderer'].get('thumbnail'):
                poster = '{}/image?width=1280&height=720&overlay=https:{}'.format(config.server, quote_plus(player_response['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['thumbnail']['thumbnails'][0]['url']))
            else:
                poster = '{}/image?width=1280&height=720&overlay={}'.format(config.server, quote_plus('https://s.ytimg.com/yts/img/meh7-vflGevej7.png'))
            item['content_html'] = utils.add_image(poster, caption)
            return item

        video_details = player_response['videoDetails']
        item['title'] = video_details['title']

        if player_response.get('microformat') and player_response['microformat'].get('playerMicroformatRenderer'):
            if player_response['microformat']['playerMicroformatRenderer'].get('publishDate'):
                # Sometimes gives full iso format with timezone, other times it's just YYYY-MM-DD
                dt_loc = datetime.fromisoformat(player_response['microformat']['playerMicroformatRenderer']['publishDate'])
                if dt_loc.tzinfo:
                    dt = dt_loc.astimezone(timezone.utc)
                else:
                    # Assume it's localized
                    tz_loc = pytz.timezone(config.local_tz)
                    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
                item['date_published'] = dt.isoformat()
                item['_timestamp'] = dt.timestamp()
                item['_display_date'] = utils.format_display_date(dt, date_only=True)

        if 'author' in args and args['author']['name'] == video_details['author']:
            item['author'] = args['author'].copy()
        else:
            item['author'] = get_author_info(video_details['channelId'])
            if not item.get('author'):
                item['author'] = {}
                item['author']['name'] = video_details['author']
                item['author']['url'] = 'https://www.youtube.com/channel/{}'.format(video_details['channelId'])
                item['author']['avatar'] = '{}/image?height=32&width=32&mask=ellipse'.format(config.server)

        if video_details.get('keywords'):
            item['tags'] = video_details['keywords'].copy()

        if video_details.get('shortDescription'):
            item['summary'] = video_details['shortDescription']

        item['_duration'] = format_duration(video_details['lengthSeconds'])

        image = utils.closest_dict(video_details['thumbnail']['thumbnails'], 'width', 1200)
        if image:
            item['_image'] = image['url']
        else:
            item['_image'] = 'https://i.ytimg.com/vi/{}/maxresdefault.jpg'.format(video_id)

        heading = '<table><tr><td style="width:32px; verticle-align:middle;"><img src="{}" /><td style="verticle-align:middle;"><a href="{}">{}</a></td></tr></table>'.format(item['author']['avatar'], item['author']['url'], item['author']['name'])
        caption = '{} | <a href="{}">Watch on YouTube</a>'.format(item['title'], item['url'])
        link = 'https://www.youtube-nocookie.com/embed/' + video_id
        poster = ''

        if player_response['playabilityStatus']['status'] == 'ERROR' or player_response['playabilityStatus']['status'] == 'UNPLAYABLE' or player_response['playabilityStatus']['status'] == 'LOGIN_REQUIRED':
            video_stream = None
            if player_response['playabilityStatus'].get('errorScreen') and player_response['playabilityStatus']['errorScreen'].get('playerErrorMessageRenderer'):
                reasons = []
                if player_response['playabilityStatus']['errorScreen']['playerErrorMessageRenderer'].get('reason'):
                    msg = player_response['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['reason']['simpleText']
                    if not msg.endswith('.'):
                        msg += '.'
                    reasons.append(msg)
                if player_response['playabilityStatus']['errorScreen']['playerErrorMessageRenderer'].get('subreason'):
                    for it in player_response['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['subreason']['runs']:
                        msg = it['text']
                        if not msg.endswith('.'):
                            msg += '.'
                        reasons.append(msg)
                if reasons:
                    caption = '<strong>' + ' '.join(reasons) + '</strong> | ' + caption
                if player_response['playabilityStatus']['errorScreen']['playerErrorMessageRenderer'].get('thumbnail'):
                    poster = '{}/image?url={}&width=1080&overlay=https:{}'.format(config.server, quote_plus(item['_image']), quote_plus(player_response['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['thumbnail']['thumbnails'][0]['url']))
        elif player_response.get('streamingData') and player_response['streamingData'].get('formats'):
            video_stream = utils.closest_dict(player_response['streamingData']['formats'], 'height', 480)
        else:
            # TODO: use adaptiveFormats?
            video_stream = None
        if video_stream:
            video_url = ''
            if video_stream.get('url'):
                video_url = video_stream['url']
            elif video_stream.get('signatureCipher'):
                sc = parse_qs(video_stream['signatureCipher'])
                if sc.get('url') and sc.get('s'):
                    if not player_url:
                        player_resp, player_url = get_player_response(video_id, True)
                    if player_url:
                        player_js = utils.get_url_html(player_url)
                        #utils.write_file(player_js, './debug/player.js')
                        if player_js:
                            # https://github.com/pytube/pytube/blob/master/pytube/extract.py#L400
                            # Need to patch cipher.py according to https://github.com/pytube/pytube/pull/1691
                            # Test video: https://www.youtube.com/watch?v=kDxPQqkSyL4
                            try:
                                cipher = Cipher(js=player_js)
                                sig = cipher.get_signature(sc['s'][0])
                                video_url = sc["url"][0] + "&sig=" + sig
                            except:
                                logger.warning('error getting decrypting signature cipher in ' + item['url'])
            if video_url:
                item['_video'] = video_url
                attachment = {}
                attachment['url'] = video_url
                if re.search(r'video/mp4', video_stream['mimeType']):
                    attachment['mime_type'] = 'video/mp4'
                elif re.search(r'video/webm', video_stream['mimeType']):
                    attachment['mime_type'] = 'video/webm'
                else:
                    attachment['mime_type'] = 'application/x-mpegURL'
                item['attachments'] = []
                item['attachments'].append(attachment)
                play_url = '{}/video?url={}'.format(config.server, quote_plus('https://www.youtube.com/watch?v=' + item['id']))
                item['content_html'] = utils.add_video(play_url, attachment['mime_type'], item['_image'], caption, heading=heading)
            else:
                logger.warning('unknown video playback url for ' + item['url'])
                video_url = 'https://www.youtube-nocookie.com/embed/' + video_id
                poster = '{}/image?url={}&width=1080&overlay=video'.format(config.server, item['_image'])
                item['content_html'] = utils.add_image(poster, caption, link=video_url, heading=heading)
        else:
            if not poster:
                poster = '{}/image?url={}&width=1080&overlay=video'.format(config.server, quote_plus(item['_image']))
            item['content_html'] = utils.add_image(poster, caption, link=link, heading=heading)

        if item.get('summary') and 'embed' not in args:
            summary_html = item['summary'].replace('\n', ' <br/> ')
            summary_html = re.sub(r'https?://([^\s]+)', r'<a href="\1">\1</a>', summary_html)
            item['content_html'] += '<p>{}</p>'.format(summary_html)

    if playlist_id:
        playlist_info = get_playlist_info(playlist_id)
        if playlist_info:
            if save_debug:
                utils.write_file(playlist_info, './debug/debug.json')
            playlist_header = playlist_info['response']['header']['playlistHeaderRenderer']
            item['id'] = playlist_id
            item['url'] = 'https://www.youtube.com/playlist?list=' + playlist_id
            item['title'] = playlist_header['title']['runs'][0]['text']
            if playlist_header.get('ownerText'):
                item['author'] = get_author_info(playlist_header['ownerText']['runs'][0]['navigationEndpoint']['browseEndpoint']['browseId'])
                if not item.get('author'):
                    item['author'] = {}
                    item['author']['name'] = playlist_header['ownerText']['runs'][0]['text']
                    item['author']['url'] = 'https://www.youtube.com' + playlist_header['ownerText']['runs'][0]['navigationEndpoint']['browseEndpoint']['canonicalBaseUrl']
                    item['author']['avatar'] = '{}/image?height=32&width=32&mask=ellipse'.format(config.server)
            item['_image'] = re.sub(r'/[^/]+\.jpg', '/maxresdefault.jpg', utils.clean_url(playlist_header['playlistHeaderBanner']['heroPlaylistThumbnailRenderer']['thumbnail']['thumbnails'][0]['url']))
            if not utils.url_exists(item['_image']):
                item['_image'] = re.sub(r'/[^/]+\.jpg', '/hqdefault.jpg', utils.clean_url(playlist_header['playlistHeaderBanner']['heroPlaylistThumbnailRenderer']['thumbnail']['thumbnails'][0]['url']))
            if not video_id:
                if item.get('author'):
                    heading = '<table><tr><td style="width:32px; verticle-align:middle;"><img src="{}" /><td style="verticle-align:middle;"><a href="{}">{}</a></td></tr></table>'.format(item['author']['avatar'], item['author']['url'], item['author']['name'])
                else:
                    heading = ''
                caption = '{} | <a href="{}">Watch on YouTube</a>'.format(item['title'], item['url'])
                link = 'https://www.youtube-nocookie.com/embed/videoseries?list=' + playlist_id
                if playlist_header.get('descriptionText') and playlist_header['descriptionText'].get('runs'):
                    item['summary'] = playlist_header['descriptionText']['runs'][0]['text']
                    desc = '<p>{}</p>'.format(item['summary'])
                else:
                    desc = ''
                item['content_html'] = utils.add_image(item['_image'], caption, link=link, heading=heading, desc=desc)
            video_list = playlist_info['response']['contents']['singleColumnBrowseResultsRenderer']['tabs'][0]['tabRenderer']['content']['sectionListRenderer']['contents'][0]['itemSectionRenderer']['contents'][0]['playlistVideoListRenderer']['contents']

    if video_list:
        item['content_html'] += '<h3><a href="https://www.youtube.com/embed/videoseries?list={}">Playlist</a></h3>'.format(playlist_id)
        video_args = {}
        if item.get('author'):
            video_args['author'] = item['author']
        if 'embed' in args:
            n = 3
        else:
            n = -1
        for i, playlist_video in enumerate(video_list):
            if i == n:
                break
            if playlist_video.get('playlistVideoRenderer'):
                video = playlist_video['playlistVideoRenderer']
                it = get_content('https://www.youtube.com/watch?v={}'.format(video['videoId']), video_args, site_json, False)
                if it:
                    if it.get('attachments'):
                        link = '{}/video?url={}'.format(config.server, quote_plus(it['url']))
                    else:
                        link = 'https://www.youtube.com/embed/' + video['videoId']
                    poster = '{}/image?height=128&url={}&overlay=video'.format(config.server, quote_plus(it['_image']))
                    desc = '<div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div><div><a href="{}">{}</a></div><div><small>{}&nbsp;&bull;&nbsp;Uploaded {}</small></div>'.format(it['url'], it['title'], it['author']['url'], it['author']['name'], it['_duration'], it['_display_date'])
                    item['content_html'] += '<table><tr><td style="width:128px;"><a href="{}"><img src="{}" style="width:100%;"/></a></td><td style="vertical-align:top;">{}</td></tr></table><div>&nbsp;</div>'.format(link, poster, desc)

    if False:
        yt_embed_url = 'https://www.youtube-nocookie.com/embed/{}'.format(video_id)
        yt_embed_html = utils.get_url_html(yt_embed_url)
        if yt_embed_html:
            soup = BeautifulSoup(yt_embed_html, 'html.parser')
            el = soup.find('script', string=re.compile(r'window\.ytcfg\.obfuscatedData_'))
            if el:
                i = el.string.find('ytcfg.set(') + 10
                j = el.string.rfind('}') + 1
                yt_cfg = json.loads(el.string[i:j])
                yt_player_resp = json.loads(yt_cfg['PLAYER_VARS']['embedded_player_response'])
                if save_debug:
                    utils.write_file(yt_cfg, './debug/youtube.json')
                    utils.write_file(yt_player_resp, './debug/debug.json')
                return None

        yt_watch_url = 'https://www.youtube.com/watch?v={}'.format(video_id)
        yt_html = utils.get_url_html(yt_watch_url)
        if not yt_html:
            return None
        if save_debug:
            utils.write_file(yt_html, './debug/youtube.html')

        m = re.search(r'ytInitialPlayerResponse = (.+?);(</script>|var)', yt_html)
        if not m:
            logger.warning('unable to extract ytInitialPlayerResponse from ' + yt_watch_url)
            return None

        # utils.write_file(m.group(1), './debug/debug.txt')

        yt_json = json.loads(m.group(1))
        if save_debug:
            utils.write_file(yt_json, './debug/youtube.json')

        item = {}
        item['id'] = video_id
        item['url'] = yt_watch_url

        if yt_json['playabilityStatus']['status'] == 'ERROR' or yt_json['playabilityStatus']['status'] == 'LOGIN_REQUIRED':
            if yt_json['playabilityStatus'].get('reason'):
                caption = yt_json['playabilityStatus']['reason']
                if yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer'].get('subreason'):
                    if yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['subreason'].get(
                            'simpleText'):
                        caption += '. ' + \
                                   yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['subreason'][
                                       'simpleText']
                    elif yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['subreason'].get('runs'):
                        caption += '. ' + \
                                   yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['subreason'][
                                       'runs'][0]['text']
            elif yt_json['playabilityStatus'].get('messages'):
                caption = ' '.join(yt_json['playabilityStatus']['messages'])
            else:
                caption = ''
            item['title'] = caption

            if yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer'].get('thumbnail'):
                overlay = \
                yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['thumbnail']['thumbnails'][0][
                    'url']
                if overlay.startswith('//'):
                    overlay = 'https:' + overlay
                poster = '{}/image?width=1280&height=720&overlay={}'.format(config.server, quote_plus(overlay))
            else:
                poster = '{}/image?width=1280&height=720&overlay=video'.format(config.server)

            item['content_html'] = utils.add_image(poster, caption, link=yt_embed_url)
            return item

        item['title'] = yt_json['videoDetails']['title']

        item['author'] = {}
        item['author']['name'] = yt_json['videoDetails']['author']

        if yt_json['videoDetails'].get('keywords'):
            item['tags'] = yt_json['videoDetails']['keywords'].copy()

        images = yt_json['videoDetails']['thumbnail']['thumbnails'] + \
                 yt_json['microformat']['playerMicroformatRenderer']['thumbnail']['thumbnails']
        image = utils.closest_dict(images, 'height', 1080)
        if image['height'] < 360:
            item['_image'] = image['url'].split('?')[0]
        else:
            item['_image'] = image['url']

        item['summary'] = yt_json['videoDetails']['shortDescription']

        if yt_json['playabilityStatus']['status'] == 'OK':
            caption = '{} | <a href="{}">Watch on YouTube</a>'.format(item['title'], item['url'])
            if playlist_id:
                caption += ' | <a href="{}&list={}">View playlist</a>'.format(yt_watch_url, playlist_id)
            poster = '{}/image?url={}&overlay=video'.format(config.server, quote_plus(item['_image']))
            item['content_html'] = utils.add_image(poster, caption, link=yt_embed_url)
        else:
            error_reason = 'Error'
            if yt_json['playabilityStatus'].get('errorScreen'):
                overlay = \
                yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['thumbnail']['thumbnails'][0][
                    'url']
                if overlay.startswith('//'):
                    overlay = 'https:' + overlay
                poster = '{}/image?url={}&overlay={}'.format(config.server, quote_plus(item['_image']), quote_plus(overlay))
                error_reason = yt_json['playabilityStatus']['errorScreen']['playerErrorMessageRenderer']['reason'][
                    'simpleText']
            else:
                poster = '{}/image?url={}'.format(config.server, quote_plus(item['_image']))
            if not error_reason and yt_json['playabilityStatus'].get('reason'):
                error_reason = yt_json['playabilityStatus']['reason']
            caption = '{} | {} | <a href="{}">Watch on YouTube</a>'.format(error_reason, item['title'], yt_embed_url)
            if playlist_id:
                caption += ' | <a href="{}&list={}">View playlist</a>'.format(yt_watch_url, playlist_id)
            item['content_html'] = utils.add_image(poster, caption, link=yt_embed_url)

        if args and 'embed' in args:
            return item

        summary_html = yt_json['videoDetails']['shortDescription'].replace('\n', ' <br /> ')

        def replace_link(matchobj):
            return '<a href="{0}">{0}</a>'.format(matchobj.group(0))

        summary_html = re.sub(r'https?:\/\/[^\s]+', replace_link, summary_html)
        item['content_html'] += '<p>{}</p>'.format(summary_html)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
