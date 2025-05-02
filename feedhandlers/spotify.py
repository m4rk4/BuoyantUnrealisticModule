import json, re, requests
import base64, curl_cffi, hashlib, pyotp, time
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlencode, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_key(file_id, save_debug=False):
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "origin": "https://embed-standalone.spotify.com",
        "referer": "https://embed-standalone.spotify.com/",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"131\", \"Chromium\";v=\"131\", \"Not_A Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
    }
    url = 'https://seektables.scdn.co/seektable/{}.json'.format(file_id)
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return 'Error {} getting {}'.format(r.status_code, url)
    seektables = r.json()
    if save_debug:
        utils.write_file(seektables, './debug/seektables.json')

    license_headers = \
'''{
    'accept': '*/*',
    'accept-language': 'en-US,en;q=0.9,en-GB;q=0.8',
    'origin': 'https://embed-standalone.spotify.com',
    'priority': 'u=1, i',
    'referrer': 'https://embed-standalone.spotify.com/',
    'sec-ch-ua': '"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0'
}'''
    cdrm_data = {
        'PSSH': seektables['pssh'],
        'License URL': 'https://spclient.wg.spotify.com/widevine-license/v1/unauth/audio/license',
        'Headers': license_headers,
        'JSON': "{}",
        'Cookies': "{}",
        'Data': "{}",
        'Proxy': "",
    }
    r = requests.post('https://cdrm-project.com/', json=cdrm_data)
    if r.status_code != 200:
        return 'Error {} getting keys from https://cdrm-project.com/'.format(r.status_code)
    cdrm_result = r.json()
    if save_debug:
        utils.write_file(cdrm_result, './debug/cdrm.json')
    key = cdrm_result['Message'].split(':')[1].strip()
    return key


# https://github.com/jdemaeyer/spoqify/blob/master/spoqify/anonymization.py
def _generate_totp(timestamp):
    # via https://github.com/kunesj/holo-spotify-stats/blob/ebdcbbb22904946ec518cbf6cac74fec94a01f64/fetch_spotify_stats.py#L129
    uint8_secret = bytearray([
        53, 53, 48, 55, 49, 52, 53, 56, 53, 51, 52, 56, 55, 52, 57, 57, 53, 57,
        50, 50, 52, 56, 54, 51, 48, 51, 50, 57, 51, 52, 55,
    ])
    secret = base64.b32encode(bytes(uint8_secret)).decode("ascii")
    period = 30
    return pyotp.hotp.HOTP(
        s=secret,
        digits=6,
        digest=hashlib.sha1,
    ).at(
        int(timestamp / period),
    )


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if split_url.netloc == 'podcasters.spotify.com':
        if 'episodes' in paths:
            content_id = paths[paths.index('episodes') + 1].split('-')[-1]
            api_url = 'https://podcasters.spotify.com/pod/api/v3/episodes/' + content_id
            api_json = utils.get_url_json(api_url)
            if not api_json:
                return None
            item = {}
            item['id'] =  api_json['episode']['episodeId']
            item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, api_json['episode']['shareLinkPath'])
            item['title'] = api_json['episode']['title']
            dt = datetime.fromisoformat(api_json['episode']['publishOn'])
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, False)
            item['author'] = {
                "name": api_json['creator']['name'],
                "url": api_json['creator']['url']
            }
            item['authors'] = []
            item['authors'].append(item['author'])
            item['image'] = api_json['podcastMetadata']['podcastImage']
            item['_audio'] = api_json['episodeAudios'][0]['audioUrl']
            attachment = {}
            attachment['url'] = item['_audio']
            attachment['mime_type'] = 'audio/mpeg'
            item['attachments'] = []
            item['attachments'].append(attachment)
            item['content_html'] = utils.add_audio(item['_audio'], item['image'], item['title'], item['url'], item['author']['name'], item['author']['url'], item['_display_date'], float(api_json['episode']['duration']) / 1000)
            return item
        elif 'show' in paths:
            # https://podcasters.spotify.com/pod/show/jimny-carpenter
            show_slug = paths[paths.index('show') + 1]
            api_url = 'https://podcasters.spotify.com/pod/api/{}/stationId'.format(show_slug)
            api_json = utils.get_url_json(api_url)
            if not api_json:
                return None
            api_url = 'https://podcasters.spotify.com/pod/api/v3/profile/' + api_json['webStationId']
            api_json = utils.get_url_json(api_url)
            if not api_json:
                return None
            if save_debug:
                utils.write_file(api_json, './debug/spotify.json')
            item = {}
            item['id'] = api_json['podcastMetadata']['spotifyShowUrl'].split('/')[-1]
            item['url'] = api_json['podcastMetadata']['spotifyShowUrl']
            item['title'] = api_json['podcastMetadata']['podcastName']
            dt = datetime.fromisoformat(api_json['episode']['publishOn'])
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, False)
            item['author'] = {
                "name": api_json['creator']['name']
            }
            item['authors'] = []
            item['authors'].append(item['author'])
            item['image'] = api_json['podcastMetadata']['podcastImage']
            poster = '{}/image?url={}&width=128'.format(config.server, quote_plus(item['image']))
            item['content_html'] = '<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:8px; margin:8px;">'
            item['content_html'] += '<div style="flex:1; min-width:128px; max-width:160px;"><a href="{}/playlist?url={}" target="_blank"><img src="{}" style="width:100%;"/></a></div>'.format(config.server, quote_plus(item['url']), poster)
            item['content_html'] += '<div style="flex:2; min-width:256px;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(item['url'], item['title'])
            item['content_html'] += '<div style="margin:4px 0 4px 0;">By {}</div>'.format(item['author']['name'])
            if item.get('summary'):
                item['content_html'] += '<div style="margin:4px 0 4px 0; font-size:0.8em;">{}</div>'.format(item['summary'])
            item['content_html'] += '</div></div>'
            item['content_html'] += '<h3>Episodes:</h3>'
            item['_playlist'] = []
            if 'max' in args:
                n = int(args['max'])
            elif 'embed' in args:
                n = 3
            else:
                n = 10
            n = min(n, len(api_json['episodes']))
            for i, episode in enumerate(api_json['episodes'][:n]):
                playback_url = ''
                if i == 0 and api_json.get('episodeAudios'):
                    playback_url = api_json['episodeAudios'][0]['audioUrl']
                elif episode.get('episodeEnclosureUrl'):
                    # playback_url = utils.get_redirect_url(episode['episodeEnclosureUrl'])
                    playback_url = episode['episodeEnclosureUrl']
                else:
                    ep_item = get_content('https://podcasters.spotify.com' + episode['shareLinkPath'], args, site_json, False)
                    if ep_item:
                        playback_url = ep_item['_audio']
                dt = datetime.fromisoformat(episode['publishOn'])
                if playback_url:
                    item['_playlist'].append({
                        "src": playback_url,
                        "name": episode['title'],
                        "artist": utils.format_display_date(dt, False),
                        "image": item['image']
                    })
                item['content_html'] += utils.add_audio(playback_url, item['image'], episode['title'], episode['shareLinkPath'], '', '', utils.format_display_date(dt, False), float(episode['duration']) / 1000, show_poster=False)
            if n < len(api_json['episodes']):
                item['content_html'] += '<div><a href="{}">View more episodes</a></div>'.format(item['url'])
            return item

    m = re.search(r'https://open\.spotify\.com/embed(-legacy|-podcast)?/([^/]+)/([0-9a-zA-Z]+)', url)
    if m:
        content_type = m.group(2)
        content_id = m.group(3)
    else:
        m = re.search(r'https://open\.spotify\.com/([^/]+)/([0-9a-zA-Z]+)', url)
        if m:
            content_type = m.group(1)
            content_id = m.group(2)
        else:
            logger.warning('unable to parse Spotify url ' + url)
            return None

    # Find web-player.xxx.js and parse needed parameters
    # Top Songs - USA playlist
    r = curl_cffi.get('https://open.spotify.com/playlist/37i9dQZEVXbLp5XoPON0wI', impersonate='chrome')
    if r.status_code == 200:
        soup = BeautifulSoup(r.text, 'lxml')
        el = soup.find('script', id='appServerConfig')
        if el:
            params = json.loads(base64.b64decode(el.string).decode())
            if params.get('correlationId'):
                cid = params['correlationId']
        el = soup.find('script', attrs={"src": re.compile(r'web-player/web-player')})
        if el:
            r = curl_cffi.get(el['src'], impersonate='chrome')
            if r and r.status_code == 200:
                web_player_js = r.text
                m = re.search(r'buildVer:"([^"]+)', web_player_js)
                if m:
                    build_version = m.group(1)
                m = re.search(r'buildDate:"([^"]+)', web_player_js)
                if m:
                    build_date = m.group(1)
                m = re.search(r'clientVersion:"([^"]+)', web_player_js)
                if m:
                    client_version = m.group(1)
                m = re.search(r'clientId:"([^"]+)', web_player_js)
                if m:
                    client_id = m.group(1)

    client_time = int(time.time() * 1000)
    server_time = client_time // 1000
    totp = _generate_totp(client_time / 1000)
    params = {
        "reason": "init",
        "productType": "web-player",
        "totp": totp,
        "totpServer": totp,
        "totpVer": 5,
        "sTime": server_time,
        "cTime": client_time,
        "buildVer": build_version,
        "buildDate": build_date
    }
    r = curl_cffi.get('https://open.spotify.com/get_access_token?' + urlencode(params), impersonate='chrome')
    if not r or r.status_code != 200:
        logger.warning('unable to get access token from https://open.spotify.com/get_access_token')
        return None
    access_data = r.json()
    access_token = access_data['accessToken']

    headers = {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "content-type": "application/json",
        "priority": "u=1, i"
    }
    data = {
        "client_data": {
            "client_version": client_version,
            "client_id": client_id,
            "js_sdk_data": {
                "device_brand": "unknown",
                "device_model": "unknown",
                "os": "windows",
                "os_version": "NT 10.0",
                "device_id": cid,
                "device_type": "computer"
            }
        }
    }
    r = curl_cffi.post('https://clienttoken.spotify.com/v1/clienttoken', json=data, impersonate='chrome', headers=headers)
    if not r or r.status_code != 200:
        logger.warning('unable to get client token from https://clienttoken.spotify.com/v1/clienttoken')
        return None
    client_data = r.json()
    if client_data['response_type'] != 'RESPONSE_GRANTED_TOKEN_RESPONSE':
        logger.warning('invalid clienttoken response_type ' + client_data['response_type'])
        return None
    client_token = client_data['granted_token']['token']

    headers = {
        "accept": "application/json",
        "accept-language": "en",
        "app-platform": "WebPlayer",
        "authorization": "Bearer " + access_token,
        "client-token": client_token,
        "content-type": "application/json;charset=UTF-8",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"131\", \"Chromium\";v=\"131\", \"Not_A Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "spotify-app-version": client_version
    }

    item = {}
    if content_type == 'track':
        extensions = {}
        m = re.search(r'(\d+):"xpui-routes-track-v2"', web_player_js)
        if m:
            m = re.search(r'{}:"([0-9a-f]+)"'.format(m.group(1)), web_player_js)
            if m:
                r = curl_cffi.get('https://open.spotifycdn.com/cdn/build/web-player/xpui-routes-track-v2.{}.js'.format(m.group(1)), impersonate='chrome')
                if r and r.status_code == 200:
                    m = re.search(r'"getTrack","query","([^"]+)', r.text)
                    if m:
                        extensions = {
                            "persistedQuery": {
                                "version": 1,
                                "sha256Hash": m.group(1)
                            }
                        }
        if not extensions:
            logger.warning('unable to find getTrack persistedQuery hash')
            return None
        variables = {
            "uri": "spotify:track:" + content_id
        }
        api_url = 'https://api-partner.spotify.com/pathfinder/v1/query?operationName=getTrack&variables=' + quote_plus(json.dumps(variables, separators=(',', ':'))) + '&extensions=' + quote_plus(json.dumps(extensions, separators=(',', ':')))
        api_json = utils.get_url_json(api_url, headers=headers)
        if not api_json:
            return None
        track = api_json['data']['trackUnion']
        album = track['albumOfTrack']
        if save_debug:
            utils.write_file(track, './debug/spotify.json')

        item['id'] = track['uri']
        item['url'] = utils.clean_url(track['sharingInfo']['shareUrl'])
        item['title'] = track['name']

        dt = datetime.fromisoformat(album['date']['isoString'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, False)

        artists = []
        item['authors'] = []
        for artist in track['firstArtist']['items'] + track['otherArtists']['items']:
            artist_url = 'https://open.spotify.com/artist/' + artist['uri'].split(':')[-1]
            item['authors'].append({"name": artist['profile']['name'], "url": artist_url})
            artists.append('<a href="{}">{}</a>'.format(artist_url, artist['profile']['name']))
        artist = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(artists))
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

        item['image'] = album['coverArt']['sources'][0]['url']

        album_url = 'https://open.spotify.com/album/' + album['uri'].split(':')[-1]
        artist += '<br/><a href="{}">{}</a>'.format(album_url, album['name'])

        playback_url = 'https://embed-standalone.spotify.com/embed/track/' + track['uri'].split(':')[-1]
        audio_type = 'audio_link'
        item['content_html'] = utils.add_audio(playback_url, item['image'], item['title'], item['url'], artist, '', 'Released: ' + item['_display_date'], -1, audio_type)

    elif content_type == 'album':
        m = re.search(r'"getAlbum","query","([^"]+)', web_player_js)
        if not m:
            logger.warning('unable to find getAlbum persistedQuery hash')
            return None
        extensions = {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": m.group(1)
            }
        }
        variables = {
            "uri": "spotify:album:" + content_id,
            "locale": "",
            "offset": 0,
            "limit": 50
        }
        api_url = 'https://api-partner.spotify.com/pathfinder/v1/query?operationName=getAlbum&variables=' + quote_plus(json.dumps(variables, separators=(',', ':'))) + '&extensions=' + quote_plus(json.dumps(extensions, separators=(',', ':')))
        api_json = utils.get_url_json(api_url, headers=headers)
        if not api_json:
            return None
        album = api_json['data']['albumUnion']
        if save_debug:
            utils.write_file(album, './debug/spotify.json')

        item['id'] = album['uri']
        item['url'] = utils.clean_url(album['sharingInfo']['shareUrl'])
        item['title'] = album['name']

        dt = datetime.fromisoformat(album['date']['isoString'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, False)

        artists = []
        item['authors'] = []
        for artist in album['artists']['items']:
            artist_url = utils.clean_url(artist['sharingInfo']['shareUrl'])
            item['authors'].append({"name": artist['profile']['name'], "url": artist_url})
            artists.append('<a href="{}">{}</a>'.format(artist_url, artist['profile']['name']))
        artist = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(artists))
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }

        item['image'] = album['coverArt']['sources'][0]['url']

        item['content_html'] = utils.add_audio('', item['image'], item['title'], item['url'], artist, '', 'Released: ' + item['_display_date'], -1)
        item['content_html'] += '<div style="margin-left:12px;">'
        for it in album['tracksV2']['items']:
            track = it['track']
            track_id = track['uri'].split(':')[-1]
            artists = []
            for artist in track['artists']['items']:
                artist_url = 'https://open.spotify.com/artist/' + artist['uri'].split(':')[-1]
                artists.append('<a href="{}">{}</a>'.format(artist_url, artist['profile']['name']))
            artist = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(artists))
            playback_url = 'https://embed-standalone.spotify.com/embed/track/' + track['uri'].split(':')[-1]
            audio_type = 'audio_link'
            item['content_html'] += utils.add_audio(playback_url, '', track['name'], 'https://open.spotify.com/track/' + track_id, artist, '', '', -1, audio_type, show_poster=False)
        item['content_html'] += '</div>'

    elif content_type == 'playlist':
        m = re.search(r'"fetchPlaylist","query","([^"]+)', web_player_js)
        if not m:
            logger.warning('unable to find fetchPlaylist persistedQuery hash')
            return None
        extensions = {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": m.group(1)
            }
        }
        variables = {
            "uri": "spotify:playlist:" + content_id,
            "offset": 0,
            "limit": 25
        }
        api_url = 'https://api-partner.spotify.com/pathfinder/v1/query?operationName=fetchPlaylist&variables=' + quote_plus(json.dumps(variables, separators=(',', ':'))) + '&extensions=' + quote_plus(json.dumps(extensions, separators=(',', ':')))
        api_json = utils.get_url_json(api_url, headers=headers)
        if not api_json:
            return None
        playlist = api_json['data']['playlistV2']
        if save_debug:
            utils.write_file(playlist, './debug/spotify.json')

        item['id'] = playlist['uri']
        item['url'] = utils.clean_url(playlist['sharingInfo']['shareUrl'])
        item['title'] = playlist['name']
    
        date = next((it for it in playlist['attributes'] if it['key'] == 'last_updated'), None)
        if date:
            dt = datetime.fromisoformat(date['value'])
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, False)

        item['author'] = {
            "name": playlist['ownerV2']['data']['name'],
            "url": 'https://open.spotify.com/user/' + playlist['ownerV2']['data']['username']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

        item['image'] = playlist['images']['items'][0]['sources'][0]['url']

        item['summary'] = playlist['description']

        item['content_html'] = utils.add_audio('', item['image'], item['title'], item['url'], item['author']['name'], item['author']['url'], 'Updated: ' + item['_display_date'], -1)

        item['content_html'] += '<div style="margin-left:12px;">'
        for it in playlist['content']['items']:
            track = it['itemV2']['data']
            track_id = track['uri'].split(':')[-1]
            artists = []
            for artist in track['artists']['items']:
                artist_url = 'https://open.spotify.com/artist/' + artist['uri'].split(':')[-1]
                artists.append('<a href="{}">{}</a>'.format(artist_url, artist['profile']['name']))
            artist = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(artists))
            playback_url = 'https://embed-standalone.spotify.com/embed/track/' + track['uri'].split(':')[-1]
            audio_type = 'audio_link'
            item['content_html'] += utils.add_audio(playback_url, track['albumOfTrack']['coverArt']['sources'][0]['url'], track['name'], 'https://open.spotify.com/track/' + track_id, artist, '', '', -1, audio_type, small_poster=True)
        item['content_html'] += '</div>'

    elif content_type == 'show':
        m = re.search(r'"queryShowMetadataV2","query","([^"]+)', web_player_js)
        if not m:
            logger.warning('unable to find queryShowMetadataV2 persistedQuery hash')
            return None
        extensions = {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": m.group(1)
            }
        }
        variables = {
            "uri": "spotify:show:" + content_id
        }
        api_url = 'https://api-partner.spotify.com/pathfinder/v1/query?operationName=queryShowMetadataV2&variables=' + quote_plus(json.dumps(variables, separators=(',', ':'))) + '&extensions=' + quote_plus(json.dumps(extensions, separators=(',', ':')))
        api_json = utils.get_url_json(api_url, headers=headers)
        if not api_json:
            return None
        show = api_json['data']['podcastUnionV2']
        if save_debug:
            utils.write_file(show, './debug/spotify.json')

        item['id'] = show['uri']
        item['url'] = utils.clean_url(show['sharingInfo']['shareUrl'])
        item['title'] = show['name']

        item['author'] = {
            "name": show['publisher']['name']
        }
        item['authors'] = []
        item['authors'].append(item['author'])

        item['tags'] = [x['title'] for x in show['topics']['items']]

        item['image'] = show['coverArt']['sources'][-1]['url']

        item['summary'] = show['htmlDescription']

        item['content_html'] = utils.add_audio('', item['image'], item['title'], item['url'], item['author']['name'], '', '', -1)

        variables = {
            "uri": "spotify:show:" + content_id,
            "offset": 0,
            "limit": 10
        }
        extensions = {
            "persistedQuery": {
                "version":1,
                "sha256Hash":"5989878c374a6c5d0fec1860968490efda78be6c4128cfedb0595be15785c68e"
            }
        }
        api_url = 'https://api-partner.spotify.com/pathfinder/v1/query?operationName=queryPodcastEpisodes&variables=' + quote_plus(json.dumps(variables, separators=(',', ':'))) + '&extensions=' + quote_plus(json.dumps(extensions, separators=(',', ':')))
        api_json = utils.get_url_json(api_url, headers=headers)
        if api_json:
            item['content_html'] += '<div style="margin-left:12px;">'
            episodes = api_json['data']['podcastUnionV2']['episodesV2']['items']
            for it in episodes:
                episode = it['entity']['data']
                dt = datetime.fromisoformat(episode['releaseDate']['isoString'])
                playback_url = 'https://embed-standalone.spotify.com/embed/episode/' + episode['id']
                audio_type = 'audio_link'
                item['content_html'] += utils.add_audio(playback_url, '', episode['name'], utils.clean_url(episode['sharingInfo']['shareUrl']), '', '', utils.format_display_date(dt, False), episode['duration']['totalMilliseconds'] / 1000, audio_type, show_poster=False)

    elif content_type == 'episode':
        m = re.search(r'"getEpisodeOrChapter","query","([^"]+)', web_player_js)
        if not m:
            logger.warning('unable to find getEpisodeOrChapter persistedQuery hash')
            return None
        extensions = {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": m.group(1)
            }
        }
        variables = {
            "uri": "spotify:episode:" + content_id
        }
        api_url = 'https://api-partner.spotify.com/pathfinder/v1/query?operationName=getEpisodeOrChapter&variables=' + quote_plus(json.dumps(variables, separators=(',', ':'))) + '&extensions=' + quote_plus(json.dumps(extensions, separators=(',', ':')))
        api_json = utils.get_url_json(api_url, headers=headers)
        if not api_json:
            return None
        episode = api_json['data']['episodeUnionV2']
        if save_debug:
            utils.write_file(episode, './debug/spotify.json')

        item['id'] = episode['uri']
        item['url'] = utils.clean_url(episode['sharingInfo']['shareUrl'])
        item['title'] = episode['name']

        dt = datetime.fromisoformat(episode['releaseDate']['isoString'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, False)

        item['author'] = {
            "name": episode['podcastV2']['data']['name'],
            "url": 'https://open.spotify.com/show/' + episode['podcastV2']['data']['uri'].split(':')[-1]
        }
        item['authors'] = []
        item['authors'].append(item['author'])

        item['image'] = episode['coverArt']['sources'][-1]['url']

        item['summary'] = episode['htmlDescription']

        playback_url = 'https://embed-standalone.spotify.com/embed/episode/' + content_id
        audio_type = 'audio_link'

        widevine = utils.get_url_json('https://spclient.wg.spotify.com/soundfinder/v1/unauth/episode/{}/com.widevine.alpha?market=US'.format(content_id), headers=headers)
        if widevine:
            item['_audio_file_id'] = widevine['fileId']
            if save_debug:
                utils.write_file(widevine, './debug/widevine.json')
            if widevine.get('passthroughUrl'):
                playback_url = widevine['passthroughUrl']
                audio_type = 'audio/mpeg'
                item['_audio'] = playback_url
                item['_audio_type'] = audio_type
                attachment = {}
                attachment['url'] = item['_audio']
                attachment['mime_type'] = audio_type
                item['attachments'] = []
                item['attachments'].append(attachment)
            elif widevine.get('url'):
                playback_url = item['url']
                audio_type = 'audio_redirect'
                item['_audio'] = widevine['url'][0]
                item['_audio_type'] = 'audio/mp4'
                item['_audio_key'] = 'deadbeefdeadbeefdeadbeefdeadbeef'
            elif widevine.get('fileId'):
                params = {
                    'version': 10000000,
                    'product': 9,
                    'platform': 39,
                    'alt': 'json'
                }
                headers['TE'] = 'Trailers'
                files_url = 'https://gew1-spclient.spotify.com/storage-resolve/v2/files/audio/interactive/11/' + widevine['fileId']
                r = requests.get(files_url, params=params, headers=headers)
                if r.status_code != 200:
                    logger.warning('requests error {} getting {}'.format(r.status_code, files_url))
                else:
                    files = r.json()
                    if save_debug:
                        utils.write_file(files, './debug/spotify_files.json')
                    playback_url = item['url']
                    audio_type = 'audio_redirect'
                    item['_audio'] = files['cdnurl'][0]
                    item['_audio_type'] = 'audio/mp4'
                    item['_audio_key'] = 'deadbeefdeadbeefdeadbeefdeadbeef'

        item['content_html'] = utils.add_audio(playback_url, item['image'], item['title'], item['url'], item['author']['name'], item['author']['url'], item['_display_date'], float(episode['duration']['totalMilliseconds']) / 1000, audio_type)
        if 'embed' in args or '/embed/' in url:
            return item
        item['content_html'] += item['summary']
    return item


def get_feed(url, args, site_json, save_debug=False):
    return None
