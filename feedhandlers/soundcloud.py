import json, math, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_soundcloud_key():
    pf = utils.get_url_html('https://www.pitchfork.com/reviews/albums/')
    if pf:
        soup = BeautifulSoup(pf, 'html.parser')
        for script in soup.find_all('script', attrs={"src": True}):
            if re.search(r'main-[0-9a-fA-F]+\.js', script['src']):
                script_js = utils.get_url_html('https://www.pitchfork.com' + script['src'])
                if script_js:
                    m = re.search(r'soundcloudKey:"([^"]+)"', script_js)
                    if m:
                        return m.group(1)
    logger.warning('unable to get soundcloud key')
    return ''


def get_item_info(sc_json):
    item = {}
    item['id'] = sc_json['id']
    item['url'] = sc_json['permalink_url']
    item['title'] = sc_json['title']

    dt = datetime.fromisoformat(sc_json['created_at'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
    dt = datetime.fromisoformat(sc_json['last_modified'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    item['author']['name'] = sc_json['user']['username']

    if sc_json.get('tag_list'):
        item['tags'] = sc_json['tag_list'].split(' ')
    else:
        item['tags'] = []
        item['tags'].append(sc_json['genre'])

    if sc_json.get('artwork_url'):
        item['_image'] = sc_json['artwork_url'].replace('-large', '-t500x500')
    return item


def get_track_content(track_id, client_id, secret_token, save_debug):
    json_url = 'https://api-v2.soundcloud.com/tracks/{}?client_id={}'.format(track_id, client_id)
    print(json_url)
    if secret_token:
        json_url += '&secret_token=' + secret_token
    track_json = utils.get_url_json(json_url)
    if not track_json:
        return None

    if save_debug:
        utils.write_file(track_json, './debug/debug.json')

    item = get_item_info(track_json)
    if not item:
        return None

    if item.get('_image'):
        poster = '{}/image?width=100&overlay=audio&url={}'.format(config.server, item['_image'])
    else:
        poster = '{}/image?width=100&height=100&color=grey&overlay=audio'.format(config.server)
    audio_url = '/audio?url=' + quote_plus(item['url'])

    item['content_html'] = '<center><table style="width:480px; border:1px solid black; border-radius:10px; border-spacing:0;">'

    stream_url = ''
    for media in track_json['media']['transcodings']:
        if media['format']['protocol'] == 'progressive':
            stream_url = media['url']
            break
    if stream_url:
        if not '?' in stream_url:
            stream_url += '?'
        else:
            stream_url += '&'
        stream_url += 'client_id={}&track_authorization={}'.format(client_id, track_json['track_authorization'])
        stream_json = utils.get_url_json(stream_url)
        item['_audio'] = stream_json['url']
        item['content_html'] += '<tr><td style="padding:0; margin:0;"><a href="{}"><img style="display:block; width:100px; border-top-left-radius:10px; border-bottom-left-radius:10px;" src="{}"></a></td>'.format(audio_url, poster)
    else:
        logger.warning('no progressive format for ' + item['url'])
        item['content_html'] += '<tr><td style="padding:0; margin:0;"><img style="display:block; width:100px; border-top-left-radius:10px; border-bottom-left-radius:10px;" src="{}"></td>'.format(poster)

    item['content_html'] += '<td style="padding-left:0.5em;"><a href="{}"><b>{}</b></a><br /><small>by <a href="{}">{}</a></small></td></tr></table></center>'.format(track_json['permalink_url'], track_json['title'], track_json['user']['permalink_url'], track_json['user']['username'])

    return item


def get_playlist_content(playlist_id, client_id, secret_token, save_debug):
    json_url = 'https://api-v2.soundcloud.com/playlists/{}?client_id={}'.format(playlist_id, client_id)
    if secret_token:
        json_url += '&secret_token=' + secret_token
    playlist_json = utils.get_url_json(json_url)
    if not playlist_json:
        return None

    if save_debug:
        utils.write_file(playlist_json, './debug/playlist.json')

    item = get_item_info(playlist_json)
    if not item:
        return None

    item['content_html'] = '<center><table style="width:480px; border:1px solid black; border-radius:10px; border-spacing: 0;">'
    if item.get('_image'):
        item['content_html'] += '<tr><td colspan="2" style="padding:0 0 1em 0; margin:0;"><img style="display:block; width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" src="{}"></td></tr>'.format(item['_image'])
        img_border = ''
    else:
        img_border = ' border-top-left-radius: 10px;'

    i = 0
    for track in playlist_json['tracks']:
        if not track.get('permalink_url'):
            continue

        if track.get('artwork_url'):
            poster = '/image?width=64&url=' + quote_plus(track['artwork_url'])
        else:
            poster = '/image?width=64&url=' + quote_plus('https://a-v2.sndcdn.com/assets/images/sc-icons/ios-a62dfc8fe7.png')

        stream_url = ''
        for media in track['media']['transcodings']:
            if media['format']['protocol'] == 'progressive':
                stream_url = media['url']
                break

        if stream_url:
            audio_url = '/audio?url=' + quote_plus(track['permalink_url'])
            # item['content_html'] += '<tr><td><audio id="track{0}" src="{1}"></audio><div><button onclick="audio=document.getElementById(\'track{0}\'); img=document.getElementById(\'icon{0}\'); if (audio.paused) {{audio.play(); img.src=\'/static/play-icon.png\'}} else {{audio.pause(); img.src=\'/static/pause-icon.png\'}}" style="border:none;"><img id="icon{0}" src="/static/pause-icon.png" style="height:64px; background-image:url(\'{2}\');" /></button></div></td>'.format(i, audio_url, poster)
            item['content_html'] += '<tr><td style="vertical-align:top; padding:0 0 1em 0; margin:0;"><a href="{}"><img src="{}" style="height:64px;{}" /></a></td>'.format(audio_url, poster, img_border)
        else:
            item['content_html'] += '<tr><td style="vertical-align:top; padding:0 0 1em 0; margin:0;"><img src="{}" style="display:block; height:64px;{}" /></td>'.format(poster, img_border)

        item['content_html'] += '<td style="vertical-align:top; padding-left:0.5em;"><b><a href="{}">{}</a></b><br /><small>by <a href="{}">{}</a></small></td></tr>'.format(track['permalink_url'], track['title'], track['user']['permalink_url'], track['user']['username'])
        img_border = ''
        i += 1

    if i < playlist_json['track_count']:
        item['content_html'] += '<tr><td colspan="2" style="text-align:center; border-top: 1px solid black;"><a href="{}">View full playlist</a></td></tr>'.format(item['url'])
    item['content_html'] += '</table></center>'
    return item


def old_content(url, args, site_json, save_debug):
    item = None
    sc_key = get_soundcloud_key()
    if not sc_key:
        return None

    sc_html = utils.get_url_html(url)
    if not sc_html:
        return None

    soup = BeautifulSoup(sc_html, 'html.parser')

    # If the url is the widget, we need to find the real url
    secret_token = ''
    if url.startswith('https://w.soundcloud.com/player/'):
        m = re.search(r'secret_token%3D([^&]+)', url)
        if m:
            secret_token = m.group(1)
        el = soup.find('link', rel='canonical')
        if el:
            sc_html = utils.get_url_html(el['href'])
            if not sc_html:
                return None
            soup = BeautifulSoup(sc_html, 'html.parser')

    # Find the client id
    client_id = ''
    for script in soup.find_all('script', src=re.compile(r'^https:\/\/a-v2\.sndcdn\.com\/assets\/\d+-\w+\.js')):
        script_html = utils.get_url_html(script['src'])
        m = re.search(r'client_id=(\w+)', script_html)
        if m:
            client_id = m.group(1)
            break

    el = soup.find('link', href=re.compile(r'^(android|ios)-app:'))
    if not el:
        return None

    m = re.search(r'\/soundcloud\/sounds:(\d+)', el['href'])
    if m:
        return get_track_content(m.group(1), client_id, secret_token, save_debug)

    m = re.search(r'\/soundcloud\/playlists:(\d+)', el['href'])
    if m:
        return get_playlist_content(m.group(1), client_id, secret_token, save_debug)

    return None


def get_content(url, args, site_json, save_debug=False):
    api_url = ''
    if url.startswith('https://api.soundcloud.com/'):
        api_url = url
    elif url.startswith('https://w.soundcloud.com/player/'):
        split_url = urlsplit(url)
        query = parse_qs(split_url.query)
        api_url = query['url'][0]
    else:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'html.parser')
        el = soup.find('meta', attrs={"property": "twitter:player"})
        if el:
            split_url = urlsplit(el['content'])
            query = parse_qs(split_url.query)
            api_url = query['url'][0]
        else:
            el = soup.find('meta', attrs={"itemprop": "embedUrl"})
            if el:
                embed_url = el['content']
                split_url = urlsplit(el['content'])
                query = parse_qs(split_url.query)
                api_url = query['url'][0]
            else:
                el = soup.find('link', href=re.compile(r'^(android|ios)-app:'))
                if el:
                    m = re.search(r'soundcloud/(\w+):(\d+)', el['href'])
                    if m:
                        if m.group(1) == 'sounds':
                            api_url = 'https://api.soundcloud.com/tracks/{}'.format(m.group(2))
                        else:
                            api_url = 'https://api.soundcloud.com/{}/{}'.format(m.group(1), m.group(2))
    if not api_url:
        logger.warning('unable to find the api url in ' + url)
        return None

    #sites_json = utils.read_json_file('./sites.json')

    widget_url = 'https://api-widget.soundcloud.com/resolve?url={}&format=json&client_id={}&app_version={}'.format(quote_plus(api_url), site_json['client_id'], site_json['app_version'])
    query = parse_qs(urlsplit(api_url).query)
    if query.get('secret_token'):
        widget_url += '&secret_token={}'.format(query['secret_token'][0])
    api_json = utils.get_url_json(widget_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/soundcloud.json')

    item = {}
    item['id'] = api_json['id']
    item['url'] = api_json['permalink_url']
    item['title'] = api_json['title']
    dt = datetime.fromisoformat(api_json['created_at'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    dt = datetime.fromisoformat(api_json['last_modified'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()
    dt = datetime.fromisoformat(api_json['display_date'].replace('Z', '+00:00'))
    item['_display_date'] = utils.format_display_date(dt, date_only=True)
    item['author'] = {}
    item['author']['name'] = api_json['user']['username']
    item['author']['url'] = api_json['user']['permalink_url']
    item['tags'] = []
    if api_json.get('genre'):
        item['tags'].append(api_json['genre'])
    if api_json.get('tag_list'):
        tag = ''
        for it in api_json['tag_list'].split(' '):
            if it.startswith('"'):
                tag = it[1:]
            elif it.endswith('"'):
                tag += ' ' + it[:-1]
                item['tags'].append(tag)
                tag = ''
            elif len(tag) > 0:
                tag += ' ' + it
            else:
                item['tags'].append(it)
    if api_json.get('artwork_url'):
        item['_image'] = api_json['artwork_url'].replace('large', 't500x500')
        poster = '{}/image?url={}&height=128'.format(config.server, item['_image'])
    elif api_json['user'].get('avatar_url'):
        item['_image'] = api_json['user']['avatar_url'].replace('large', 't500x500')
        poster = '{}/image?url={}&height=128'.format(config.server, item['_image'])
    else:
        #item['_image'] = '{}/image?height=500&width=500'.format(config.server)
        #poster = '{}/image?height=128&width=128'.format(config.server)
        item['_image'] = 'https://d21buns5ku92am.cloudfront.net/26628/images/419678-1x1_SoundCloudLogo_wordmark-341a25-original-1645807040.jpg'
        poster = '{}/image?url={}&height=128'.format(config.server, item['_image'])
    if api_json.get('description'):
        item['summary'] = api_json['description']

    if api_json['kind'] == 'track':
        media = next((it for it in api_json['media']['transcodings'] if it['format']['protocol'] == 'progressive'), None)
        if not media:
            media = next((it for it in api_json['media']['transcodings'] if (it['format']['protocol'] == 'hls' and it['preset'].startswith('mp3'))), None)
        if media:
            media_url = media['url']
            if urlsplit(media_url).query:
                media_url += '&client_id=' + site_json['client_id']
            else:
                media_url += '?client_id=' + site_json['client_id']
            audio_json = utils.get_url_json(media_url)
            if audio_json:
                item['_audio'] = audio_json['url']

        item['content_html'] = utils.add_audio_v2(item['_audio'], item['_image'], item['title'], item['url'], item['author']['name'], item['author']['url'], item['_display_date'], float(api_json['duration']) / 1000, icon_logo=config.icon_soundcloud)
    
        if 'embed' not in args and api_json.get('description'):
            item['content_html'] += '<p>{}</p>'.format(api_json['description'])

    elif api_json['kind'] == 'playlist':
        poster = '<img src="{}"/>'.format(poster)
        item['content_html'] = '<table style="width:90%; max-width:496px; margin-left:auto; margin-right:auto;"><tr><td style="width:128px;">{}</td><td style="vertical-align:top;"><a href="{}"><b>{}</b></a><br/>by <a href="{}">{}</a><br/><small>released {}</small></td></tr><table>'.format(poster, item['url'], item['title'], item['author']['url'], item['author']['name'], item['_display_date'])

        item['content_html'] += '<table style="width:90%; max-width:496px; margin-left:auto; margin-right:auto;">'
        for i, track in enumerate(api_json['tracks']):
            if track.get('title'):
                track_json = track
            else:
                api_url = 'https://api.soundcloud.com/tracks/{}'.format(track['id'])
                widget_url = 'https://api-widget.soundcloud.com/resolve?url={}&format=json&client_id={}&app_version={}'.format(quote_plus(api_url), site_json['client_id'], site_json['app_version'])
                track_json = utils.get_url_json(widget_url)
            item['content_html'] += '<tr><td style="width:1em;">{}.</td><td style="width:1em;">'.format(i+1)
            media = next((it for it in track_json['media']['transcodings'] if it['format']['protocol'] == 'progressive'), None)
            if not media:
                media = next((it for it in track_json['media']['transcodings'] if (it['format']['protocol'] == 'hls' and it['preset'].startswith('mp3'))), None)
            if media:
                audio_json = utils.get_url_json(media['url'] + '?client_id=' + site_json['client_id'])
                if audio_json:
                    item['content_html'] += '<a href="{}/openplayer?url={}&content_type=audio&poster={}" style="text-decoration:none;">'.format(config.server, quote_plus(track_json['uri']), quote_plus(track_json['artwork_url'].replace('large', 't500x500')))
                    if media['snipped']:
                        item['content_html'] += '&#9655;</a>'
                    else:
                        item['content_html'] += '&#9654;</a>'
            item['content_html'] += '</td><td style="width:99%;"><a href="{}">{}</a>'.format(track_json['permalink_url'], track_json['title'])
            if track_json['user']['id'] != api_json['user']['id']:
                item['content_html'] += ' by <a href="{}" style="text-decoration:none;">{}</a>'.format(track_json['user']['permalink_url'], track_json['user']['username'])
            item['content_html'] += '</td></tr>'
            if track_json.get('tag_list'):
                tag = ''
                for it in track_json['tag_list'].split(' '):
                    if it.startswith('"'):
                        tag = it[1:]
                    elif it.endswith('"'):
                        tag += ' ' + it[:-1]
                        if tag not in item['tags']:
                            item['tags'].append(tag)
                        tag = ''
                    elif len(tag) > 0:
                        tag += ' ' + it
                    else:
                        if it not in item['tags']:
                            item['tags'].append(it)
        item['content_html'] += '</table>'

    if not item.get('tags'):
        del item['tags']
    return item


def get_feed(url, args, site_json, save_debug):
    # For podcasts: https://feeds.soundcloud.com/users/soundcloud:users:58576458/sounds.rss
    return rss.get_feed(url, args, site_json, save_debug, get_content)
