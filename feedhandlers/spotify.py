import base64, hashlib, hmac, json, math, re
import curl_cffi, requests, rnet
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlencode, urlsplit
from ytmusicapi import YTMusic

import config, utils
from feedhandlers import odesli, ytdl

import logging

logger = logging.getLogger(__name__)


def get_ytmusic_audio(track_id):
    r = requests.get('https://api.song.link/v1-alpha.1/links?type=song&platform=spotify&id=' + track_id + '&userCountry=US')
    if r.status_code == 200:
        songlink = r.json()
        for key, val in songlink['entitiesByUniqueId'].items():
            if key.startswith('YOUTUBE'):
                return 'https://music.youtube.com/watch?v=' + val['id']
    return ''


def get_key(file_id, save_debug=False):
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "origin": "https://open.spotify.com",
        "referer": "https://open.spotify.com/",
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


def get_server_cfg():
    # Find web-player.xxx.js and parse needed parameters
    # r = curl_cffi.get('https://open.spotify.com/', impersonate='chrome', proxies=config.proxies)
    if r.status_code != 200:
        logger.warning('unable to get https://open.spotify.com/')
        return None

    client = rnet.blocking.Client()
    try:
        r = client.get('https://open.spotify.com/', emulation=rnet.Emulation.Safari26, proxy=rnet.Proxy.all(config.http_proxy))
        r.raise_for_status()
    except Exception as e:
        logger.warning('unable to get https://open.spotify.com/ ' + str(r.status))
        return None

    soup = BeautifulSoup(r.text(), 'lxml')
    el = soup.find('script', id='appServerConfig')
    if not el:
        return None
    return json.loads(base64.b64decode(el.string.strip()).decode("utf-8"))


# Credit: https://github.com/glomatico/votify/blob/main/votify/totp.py
# and https://github.com/akashrchandran/syrics/blob/main/syrics/totp.py
def get_secret_version() -> tuple[str, int]:
    r = requests.get(config.SECRET_CIPHER_DICT_URL)
    if r.status_code != 200:
        logger.warning('Failed to fetch TOTP secret and version.')
        return None
    data = r.json()
    secret_version = list(data.keys())[-1]
    ascii_codes = data[secret_version]
    transformed = [val ^ ((i % 33) + 9) for i, val in enumerate(ascii_codes)]
    secret_key = "".join(str(num) for num in transformed)
    return bytes(secret_key, 'utf-8'), secret_version


def generate_totp(timestamp: int, secret: str) -> str:
    PERIOD = 30
    DIGITS = 6
    counter = math.floor(timestamp / 1000 / PERIOD)
    counter_bytes = counter.to_bytes(8, byteorder="big")
    h = hmac.new(secret, counter_bytes, hashlib.sha1)
    hmac_result = h.digest()
    offset = hmac_result[-1] & 0x0F
    binary = (
        (hmac_result[offset] & 0x7F) << 24
        | (hmac_result[offset + 1] & 0xFF) << 16
        | (hmac_result[offset + 2] & 0xFF) << 8
        | (hmac_result[offset + 3] & 0xFF)
    )
    return str(binary % (10**DIGITS)).zfill(DIGITS)


def get_tokens(server_cfg=None):
    tokens = {}
    if not server_cfg:
        server_cfg = get_server_cfg()
        if not server_cfg:
            return None

    tokens['clientVersion'] = server_cfg['clientVersion']
    tokens['deviceId'] = server_cfg['correlationId']

    r = requests.get('https://open.spotify.com/api/server-time')
    if r.status_code != 200:
        logger.warning('unable to get server time from https://open.spotify.com/api/server-time')
        return None
    server_time = 1e3 * r.json()["serverTime"]
    totp_secret, totp_version = get_secret_version()
    totp = generate_totp(server_time, totp_secret)
    params = {
        'reason': 'init',
        'productType': 'web-player',
        'totp': totp,
        'totpServer': totp,
        'totpVer': totp_version,
    }

    # r = curl_cffi.get('https://open.spotify.com/api/token?' + urlencode(params), impersonate='chrome', proxies=config.proxies)
    # if not r or r.status_code != 200:
    #     logger.warning('unable to get access token from https://open.spotify.com/api/token')
    #     return None
    client = rnet.blocking.Client()
    try:
        r = client.get('https://open.spotify.com/api/token?' + urlencode(params), emulation=rnet.Emulation.Safari26, proxy=rnet.Proxy.all(config.http_proxy))
        r.raise_for_status()
    except Exception as e:
        logger.warning('unable to get access token from https://open.spotify.com/api/token')
        return None

    access_token = r.json()
    tokens['access_token'] = access_token['accessToken']
    tokens['clientId'] = access_token['clientId']

    headers = {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "pragma": "no-cache",
        "priority": "u=1, i"
    }
    data = {
        "client_data": {
            "client_version": tokens['clientVersion'],
            "client_id": tokens['clientId'],
            "js_sdk_data": {
                "device_brand": "unknown",
                "device_id": tokens['deviceId'],
                "device_model": "unknown",
                "device_type": "computer",
                "os": "windows",
                "os_version": "NT 10.0"
            }
        }
    }
    # print(json.dumps(data, indent=4))

    # r = curl_cffi.post('https://clienttoken.spotify.com/v1/clienttoken', json=data, impersonate='chrome', headers=headers, proxies=config.proxies)
    # if r.status_code != 200:
    #     logger.warning('unable to get client token from https://clienttoken.spotify.com/v1/clienttoken')
    #     return None
    try:
        r = client.post('https://clienttoken.spotify.com/v1/clienttoken', json=data, emulation=rnet.Emulation.Safari26, headers=headers, proxy=rnet.Proxy.all(config.http_proxy))
        r.raise_for_status()
    except Exception as e:
        logger.warning('unable to get client token from https://clienttoken.spotify.com/v1/clienttoken')
        return None

    clienttoken = r.json()
    if clienttoken['response_type'] != 'RESPONSE_GRANTED_TOKEN_RESPONSE':
        logger.warning('invalid clienttoken response_type ' + clienttoken['response_type'])
        return None
    tokens['client_token'] = clienttoken['granted_token']['token']
    return tokens


def get_embed_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    embed_url = 'https://open.spotify.com/embed/' + paths[-2] + '/' + paths[-1]
    embed_html = utils.get_url_html(embed_url, user_agent='googlebot')
    if not embed_html:
        return None
    soup = BeautifulSoup(embed_html, 'lxml')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + embed_url)
        return None

    next_data = json.loads(el.string)
    if save_debug:
        utils.write_file(next_data, './debug/next.json')
    data_entity = next_data['props']['pageProps']['state']['data']['entity']
    entity_uri = next_data['props']['pageProps']['state']['data']['embeded_entity_uri'].split(':')
    content_type = entity_uri[1]

    item = {}
    item['id'] = entity_uri[-1]
    item['url'] = 'https://open.spotify.com/' + '/'.join(entity_uri[1:])
    item['title'] = data_entity['title']
    if data_entity.get('releaseDate') and data_entity['releaseDate'].get('isoString'):
        dt = datetime.fromisoformat(data_entity['releaseDate']['isoString'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt, date_only=True)
    image = utils.closest_dict(data_entity['visualIdentity']['image'], 'maxWidth', 640)
    item['image'] = image['url']

    if content_type == 'track' or content_type == 'episode':
        if data_entity.get('artists'):
            item['authors'] = [{"name": x['name'], "url": "https://open.spotify.com/artist/" + x['uri'].split(':')[-1]} for x in data_entity['artists']]
            if len(item['authors']) > 1:
                item['author'] = {
                    "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
                }
            elif len(item['authors']) == 1:
                item['author'] = item['authors'][0]
        elif data_entity.get('subtitle'):
            item['author'] = {
                "name": data_entity['subtitle'],
            }
            if data_entity.get('relatedEntityUri'):
                item['author']['url'] = 'https://open.spotify.com/' + '/'.join(data_entity['relatedEntityUri'].split(':')[1:])
        if next_data['props']['pageProps']['state']['data'].get('defaultAudioFileObject') and next_data['props']['pageProps']['state']['data']['defaultAudioFileObject'].get('url'):
            item['_audio'] = next_data['props']['pageProps']['state']['data']['defaultAudioFileObject']['url'][-1]
            item['_audio_type'] = 'audio/mpeg'
        elif data_entity.get('audioPreview'):
            item['_audio'] = data_entity['audioPreview']['url']
            item['_audio_type'] = 'audio/mpeg'
        else:
            item['_audio'] = 'https://open.spotify.com/embed/track/' + item['id']
            item['_audio_type'] = 'audio_link'
        item['content_html'] = utils.add_audio_v2(item['_audio'], item['image'], item['title'], item['url'], item['author']['name'], item['author'].get('url'), item['_display_date'], utils.calc_duration(data_entity['duration'] / 1000, True, ':'), audio_type=item['_audio_type'])
        return item

    elif content_type == 'album' or content_type == 'playlist':
        if data_entity.get('subtitle'):
            item['author'] = {
                "name": data_entity['subtitle']
            }
        item['_playlist'] = []
        tracks_html = '<details><summary style="font-weight:bold;">Tracks:</summary>'
        for i, track in enumerate(data_entity['trackList'], 1):
            track_url = 'https://open.spotify.com/track/' + track['uri'].split(':')[-1]
            track_title = str(i) + '. ' + '<a href="' + track_url + '" target="_blank">' + track['title'] + '</a>'
            if track['isExplicit']:
                track_title += ' 🄴'
            if track.get('audioPreview'):
                tracks_html += utils.add_audio_v2(track['audioPreview']['url'], item['image'], track_title, '', track['subtitle'], '', item.get('_display_date'), utils.calc_duration(track['duration'] / 1000, True, ':'), audio_type='audio/mpeg', show_poster=False, border=False, margin='1em auto 1em auto')
                item['_playlist'].append({
                    "src": track['audioPreview']['url'],
                    "name": track_title,
                    "artist": track['subtitle'],
                    "image": item['image']
                })
            else:
                audio_src = 'https://open.spotify.com/embed/track/' + track['uri'].split(':')[-1]
                tracks_html += utils.add_audio_v2(audio_src, item['image'], track_title, '', track['subtitle'], '', item.get('_display_date'), utils.calc_duration(track['duration'] / 1000, True, ':'), audio_type='audio_link', show_poster=False, border=False, margin='1em auto 1em auto')
        tracks_html += '</details>'
        item['content_html'] = utils.add_audio_v2(config.server + '/playlist?url=' + quote_plus(item['url']), item['image'], item['title'], item['url'], item['author']['name'], item['author'].get('url'), '', '', audio_type='audio_link', desc=tracks_html)
        return item


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    if split_url.netloc == 'podcasters.spotify.com' or split_url.netloc == 'creators.spotify.com':
        if 'episodes' in paths:
            # https://creators.spotify.com/pod/profile/adeptenglish/episodes/Stop-Translating--Start-Thinking-in-English---Rule-57-e3354j2
            content_id = paths[paths.index('episodes') + 1].split('-')[-1]
            api_url = 'https://' + split_url.netloc + '/pod/api/v3/episodes/' + content_id
            api_json = utils.get_url_json(api_url)
            if not api_json:
                return None
            if save_debug:
                utils.write_file(api_json, './debug/spotify.json')
            item = {}
            item['id'] =  api_json['episode']['episodeId']
            item['url'] = 'https://' + split_url.netloc + '/pod/profile' + api_json['episode']['shareLinkPath']
            item['title'] = api_json['episode']['title']
            dt = datetime.fromisoformat(api_json['episode']['publishOn'])
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, date_only=True)
            item['author'] = {
                "name": api_json['creator']['name'],
                "url": api_json['creator']['url']
            }
            item['authors'] = []
            item['authors'].append(item['author'])
            item['image'] = api_json['podcastMetadata']['podcastImage']
            item['summary'] = api_json['episode']['description']
            if 'embed' not in args and '/embed/' not in url:
                desc = item['summary']
            else:
                desc = ''
            if api_json.get('episodeAudios'):
                item['_audio'] = api_json['episodeAudios'][0]['audioUrl']
            elif api_json['episode'].get('episodeEnclosureUrl'):
                item['_audio'] = api_json['episode']['episodeEnclosureUrl']
            if '_audio' in item:
                attachment = {}
                attachment['url'] = item['_audio']
                attachment['mime_type'] = 'audio/mpeg'
                item['attachments'] = []
                item['attachments'].append(attachment)
                item['content_html'] = utils.add_audio_v2(item['_audio'], item['image'], item['title'], item['url'], item['author']['name'], item['author']['url'], item['_display_date'], float(api_json['episode']['duration']) / 1000, desc=desc)
            else:
                item['content_html'] = utils.add_audio_v2('', item['image'], item['title'], item['url'], item['author']['name'], item['author']['url'], item['_display_date'], float(api_json['episode']['duration']) / 1000, desc=desc, button_overlay=config.lock_button_overlay)
            return item
        elif 'show' in paths or 'profile' in paths:
            # https://creators.spotify.com/pod/profile/adeptenglish/
            # show_slug = paths[paths.index('show') + 1]
            api_url = 'https://' + split_url.netloc + '/pod/api/' + paths[-1] + '/stationId'
            api_json = utils.get_url_json(api_url)
            if not api_json:
                return None
            api_url = 'https://' + split_url.netloc + '/pod/api/v3/profile/' + api_json['webStationId']
            api_json = utils.get_url_json(api_url)
            if not api_json:
                return None
            if save_debug:
                utils.write_file(api_json, './debug/spotify.json')
            item = {}
            item['id'] = api_json['podcastMetadata']['spotifyShowUrl'].split('/')[-1]
            item['url'] = 'http://' + split_url.netloc + '/pod/profile/' + api_json['creator']['vanitySlug']
            item['title'] = api_json['podcastMetadata']['podcastName']
            dt = datetime.fromisoformat(api_json['episode']['publishOn'])
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, date_only=True)
            item['author'] = {
                "name": api_json['creator']['name'],
                "url": api_json['creator']['url']
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
                    print('https://' + split_url.netloc + '/pod/profile' + episode['shareLinkPath'])
                    ep_item = get_content('https://' + split_url.netloc + '/pod/profile' + episode['shareLinkPath'], args, site_json, False)
                    if ep_item:
                        playback_url = ep_item['_audio']
                dt = datetime.fromisoformat(episode['publishOn'])
                if playback_url:
                    item['_playlist'].append({
                        "src": playback_url,
                        "name": episode['title'],
                        "artist": utils.format_display_date(dt, date_only=True),
                        "image": item['image']
                    })
                item['content_html'] += utils.add_audio(playback_url, item['image'], episode['title'], episode['shareLinkPath'], '', '', utils.format_display_date(dt, date_only=True), float(episode['duration']) / 1000, show_poster=False)
            if n < len(api_json['episodes']):
                item['content_html'] += '<div><a href="{}">View more episodes</a></div>'.format(item['url'])
            return item

    if split_url.path.startswith('/embed'):
        embed_url = 'https://open.spotify.com' + split_url.path
    else:
        embed_url = 'https://open.spotify.com/embed' + split_url.path
    r = requests.get(embed_url, headers={"user-agent": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Googlebot/2.1; +http://www.google.com/bot.html) Chrome/144.0.0.0 Safari/537.36"})
    if r.status_code == 200:
        embed_soup = BeautifulSoup(r.text, 'lxml')
        el = embed_soup.find('script', id='__NEXT_DATA__')
        if el:
            next_data = json.loads(el.string)
            if save_debug:
                utils.write_file(next_data, './debug/spotify.json')
            entity_type = next_data['props']['pageProps']['state']['data']['embeded_entity_uri'].split(':')[1]
            entity = next_data['props']['pageProps']['state']['data']['entity']
            item = {}
            item['id'] = entity['uri']
            item['url'] = entity['uri'].replace(':', '/').replace('spotify', 'https://open.spotify.com')
            item['title'] = entity['title']
            dt = None
            if entity.get('releaseDate'):
                dt = datetime.fromisoformat(entity['releaseDate']['isoString'])
            elif entity.get('attributes'):
                attr = next((it for it in entity['attributes'] if it['key'] == 'last_updated'), None)
                if attr:
                    dt = datetime.fromisoformat(attr['value'])
            if dt:
                item['date_published'] = dt.isoformat()
                item['_timestamp'] = dt.timestamp()
                item['_display_date'] = utils.format_display_date(dt, date_only=True)

            if entity.get('artists'):
                item['authors'] = [{"name": x['name'], "url": x['uri'].replace(':', '/').replace('spotify', 'https://open.spotify.com')} for x in entity['artists']]
                item['author'] = {
                    "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
                }
            elif entity.get('subtitle'):
                item['author'] = {
                    "name": entity['subtitle']
                }
                if entity.get('relatedEntityUri'):
                    item['author']['url'] = entity['relatedEntityUri'].replace(':', '/').replace('spotify', 'https://open.spotify.com')
                item['authors'] = []
                item['authors'].append(item['author'])
            if entity['visualIdentity'].get('image'):
                item['image'] = utils.closest_dict(entity['visualIdentity']['image'], 'maxWidth', 640)['url']
            elif entity.get('coverArt') and entity['coverArt'].get('sources'):
                item['image'] = entity['coverArt']['sources'][-1]['url']

            if entity_type == 'track':
                if entity.get('audioPreview'):
                    attachment = {}
                    attachment['url'] = entity['audioPreview']['url']
                    attachment['mime_type'] = 'audio/mpeg'
                    item['attachments'] = []
                    item['attachments'].append(attachment)
                item['_duration'] = utils.calc_duration(entity['duration']/1000, time_format=':')
                yt_link = get_ytmusic_audio(entity['id'])
                if yt_link:
                    item['_audio'] = config.server + '/audio?url=' + quote_plus(yt_link)
                    item['_audio'] = 'audio_link'
                else:
                    if entity.get('audioPreview'):
                        item['_audio'] = entity['audioPreview']['url']
                        item['_audio_type'] = 'audio/mpeg'
            elif entity_type == 'album' or entity_type == 'playlist':
                item['_playlist'] = []
                for it in entity['trackList']:
                    track = {
                        "url": it['uri'].replace(':', '/').replace('spotify', 'https://open.spotify.com'),
                        "title": it['title'],
                        "image": item['image'],
                        "duration": utils.calc_duration(it['duration']/1000, time_format=':')
                    }
                    if it['subtitle'] != entity['subtitle']:
                        track['artist'] = it['subtitle']
                    yt_link = get_ytmusic_audio(it['uri'].split(':')[-1])
                    if yt_link:
                        track['src'] = config.server + '/audio?url=' + quote_plus(yt_link)
                        track['mime_type'] = 'audio_link'
                    elif it.get('audioPreview'):
                        track['src'] = it['audioPreview']['url']
                        track['mime_type'] = 'audio/mpeg'
                    item['_playlist'].append(track)
            elif entity_type == 'episode':
                item['_duration'] = utils.calc_duration(entity['duration']/1000, time_format=':')
                if next_data['props']['pageProps']['state']['data'].get('defaultAudioFileObject'):
                    if next_data['props']['pageProps']['state']['data']['defaultAudioFileObject'].get('passthroughUrl'):
                        item['_audio'] = next_data['props']['pageProps']['state']['data']['defaultAudioFileObject']['passthroughUrl']
                        item['_audio_type'] = 'audio/mpeg'
                        attachment = {}
                        attachment['url'] = item['_audio']
                        attachment['mime_type'] = item['_audio_type']
                        item['attachments'] = []
                        item['attachments'].append(attachment)
                    else:
                        if entity['relatedEntityUri'].startswith('spotify:show'):
                            logger.debug('getting content from https://odesli.co/podcast/s/' + entity['relatedEntityUri'].split(':')[-1])
                            podcast_item = odesli.get_content('https://odesli.co/podcast/s/' + entity['relatedEntityUri'].split(':')[-1], {"embed": True}, {}, save_debug)
                            if podcast_item:
                                for track in podcast_item['_playlist']:
                                    if re.sub(r'\W', '', track['title']).lower() == re.sub(r'\W', '', item['title']).lower():
                                        item['_audio'] = track['src']
                                        item['_audio_type'] = track['mime_type']
                                        attachment = {}
                                        attachment['url'] = item['_audio']
                                        attachment['mime_type'] = item['_audio_type']
                                        item['attachments'] = []
                                        item['attachments'].append(attachment)
                                        break
            elif entity_type == 'show':
                logger.debug('getting content from https://odesli.co/podcast/s/' + next_data['props']['pageProps']['state']['data']['embeded_entity_uri'].split(':')[-1])
                podcast_item = odesli.get_content('https://odesli.co/podcast/s/' + next_data['props']['pageProps']['state']['data']['embeded_entity_uri'].split(':')[-1], {"embed": True}, {}, save_debug)
                item['id'] = next_data['props']['pageProps']['state']['data']['embeded_entity_uri']
                item['url'] = next_data['props']['pageProps']['state']['data']['embeded_entity_uri'].replace(':', '/').replace('spotify', 'https://open.spotify.com')
                item['title'] = entity['subtitle']
                item['author'] = podcast_item['author'].copy()
                item['authors'] = podcast_item['authors'].copy()
                item['_playlist'] = podcast_item['_playlist'].copy()
                item['_playlist_title'] = podcast_item['_playlist_title']
            item['content_html'] = utils.format_audio_content(item, logo=config.logo_spotify)
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

    # web_player_js = get_web_player_js()
    # Find web-player.xxx.js and parse needed parameters
    server_cfg = None
    web_player_js = ''
    # r = curl_cffi.get('https://open.spotify.com/', impersonate='chrome', proxies=config.proxies)
    # if r.status_code == 200:

    client = rnet.blocking.Client()
    try:
        r = client.get('https://open.spotify.com/', emulation=rnet.Emulation.Safari26, proxy=rnet.Proxy.all(config.http_proxy))
        r.raise_for_status()
    except Exception as e:
        logger.warning('unable to get https://open.spotify.com/ ' + str(r.status))
        r = None

    if r:
        soup = BeautifulSoup(r.text(), 'lxml')
        el = soup.find('script', id='appServerConfig')
        if el:
            server_cfg = json.loads(base64.b64decode(el.string.strip()).decode("utf-8"))
        el = soup.find('script', src=re.compile(r'/web-player/web-player\.([^\.]+)\.js'))
        if el:
            r = requests.get(el['src'])
            if r.status_code == 200:
                web_player_js = r.text
    if not server_cfg:
        logger.warning('unable to find appServerConfig in ' + url)
        return get_embed_content(url, args, site_json, save_debug)
    if save_debug:
        utils.write_file(server_cfg, './debug/servercfg.json')

    tokens = get_tokens(server_cfg)
    if not tokens:
        return get_embed_content(url, args, site_json, save_debug)

    headers = {
        "accept": "application/json",
        "accept-language": "en",
        "app-platform": "WebPlayer",
        "authorization": "Bearer " + tokens['access_token'],
        "cache-control": "no-cache",
        "client-token": tokens['client_token'],
        "content-type": "application/json;charset=UTF-8",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"141\", \"Not?A_Brand\";v=\"8\", \"Chromium\";v=\"141\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "spotify-app-version": tokens['clientVersion']
    }

    item = {}
    if content_type == 'track':
        extensions = {}
        m = re.search(r'(\d+):"xpui-routes-track-v2"', web_player_js)
        if m:
            m = re.search(r'{}:"([0-9a-f]+)"'.format(m.group(1)), web_player_js)
            if m:
                r = curl_cffi.get('https://open.spotifycdn.com/cdn/build/web-player/xpui-routes-track-v2.{}.js'.format(m.group(1)), impersonate='chrome', proxies=config.proxies)
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
        if album.get('date'):
            dt = datetime.fromisoformat(album['date']['isoString'])
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, date_only=True)
        artists = []
        item['authors'] = []
        for artist in track['firstArtist']['items'] + track['otherArtists']['items']:
            artist_url = 'https://open.spotify.com/' + '/'.join(artist['uri'].split(':')[1:])
            item['authors'].append({"name": artist['profile']['name'], "url": artist_url})
            artists.append('<a href="{}">{}</a>'.format(artist_url, artist['profile']['name'].replace(',', '&#44;')))
        artist = []
        artist.append(re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(artists)).replace('&#44;', ','))
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']])).replace('&#44;', ',')
        }
        item['image'] = album['coverArt']['sources'][0]['url']
        artist.append('<a href="https://open.spotify.com/album/' + album['uri'].split(':')[-1] + '">' + album['name'] + '</a>')
        playback_url = get_ytmusic_audio(track)
        if playback_url:
            logger.debug('getting audio from ' + playback_url)
            yt_item = ytdl.get_content(playback_url, {}, {"module": "ytdl"}, False)
            if yt_item and '_audio' in yt_item:
                item['_audio'] = yt_item['_audio']
                item['_audio_type'] = yt_item['_audio_type']
            playback_url = config.server + '/audio?url=' + quote_plus(playback_url)
        else:
            playback_url = 'https://open.spotify.com/embed/track/' + track['uri'].split(':')[-1]
        item['content_html'] = utils.add_audio_v2(playback_url, item['image'], item['title'], item['url'], artist, '', 'Released: ' + item['_display_date'], -1, audio_type='audio_link')

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
        item['_display_date'] = utils.format_display_date(dt, date_only=True)
        artists = []
        item['authors'] = []
        for artist in album['artists']['items']:
            artist_url = utils.clean_url(artist['sharingInfo']['shareUrl'])
            item['authors'].append({"name": artist['profile']['name'], "url": artist_url})
            artists.append('<a href="{}">{}</a>'.format(artist_url, artist['profile']['name']))
        album_artist = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(artists))
        item['author'] = {
            "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
        }
        item['image'] = album['coverArt']['sources'][0]['url']
        item['_playlist'] = []
        tracks_html = '<details><summary style="font-weight:bold;">Tracks:</summary>'
        for it in album['tracksV2']['items']:
            track = it['track']
            track_id = track['uri'].split(':')[-1]
            track_title = track['name']
            track_url = 'https://open.spotify.com/track/' + track_id
            track_title_url = '<a href="{}">{}</a>'.format(track_url, track_title)
            if 'contentRating' in track and track['contentRating']['label'] == 'EXPLICIT':
                track_title += ' 🄴'
                track_title_url += ' 🄴'
            if item['author']['name'] == re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['profile']['name'] for x in track['artists']['items']])):
                artist = ''
            else:
                artists = []
                for artist in track['artists']['items']:
                    artist_url = 'https://open.spotify.com/artist/' + artist['uri'].split(':')[-1]
                    artists.append('<a href="{}">{}</a>'.format(artist_url, artist['profile']['name']))
                artist = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(artists))
            if 'duration' in track:
                duration = utils.calc_duration(track['duration']['totalMilliseconds'] / 1000, include_sec=True, time_format=':')
            else:
                duration = -1
            playback_url = config.server + '/audio?url=' + quote_plus(track_url)
            # playback_url = get_ytmusic_audio(track)
            # if playback_url:
            #     playback_url = config.server + '/audio?url=' + quote_plus(playback_url)
            # else:
            #     playback_url = 'https://open.spotify.com/embed/track/' + track['uri'].split(':')[-1]
            tracks_html += utils.add_audio_v2(playback_url, '', track_title_url, '', artist, '', '', duration, 'audio_link', show_poster=False, border=False, margin='1em auto 1em auto')
            item['_playlist'].append({
                "src": playback_url + '&novideojs',
                "name": track_title,
                "artist": re.sub(r'<a [^>]+>|</a>', '', artist),
                "image": item['image']
            })
        tracks_html += '</details>'
        playback_url = config.server + '/playlist?url=' + quote_plus(item['url'])
        item['content_html'] = utils.add_audio_v2(playback_url, item['image'], item['title'], item['url'], album_artist, '', 'Released: ' + item['_display_date'], -1, 'audio_link', desc=tracks_html)

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
            "enableWatchFeedEntrypoint": False,
            "limit": 25,
            "offset": 0,
            "uri": "spotify:playlist:" + content_id
        }
        api_url = 'https://api-partner.spotify.com/pathfinder/v1/query?operationName=fetchPlaylist&variables=' + quote_plus(json.dumps(variables, separators=(',', ':'))) + '&extensions=' + quote_plus(json.dumps(extensions, separators=(',', ':')))
        api_json = utils.get_url_json(api_url, headers=headers)
        if not api_json:
            return None
        if save_debug:
            utils.write_file(api_json, './debug/spotify.json')
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
            item['_display_date'] = utils.format_display_date(dt, date_only=True)
        item['author'] = {
            "name": playlist['ownerV2']['data']['name'],
            "url": 'https://open.spotify.com/user/' + playlist['ownerV2']['data']['username']
        }
        item['authors'] = []
        item['authors'].append(item['author'])
        item['image'] = playlist['images']['items'][0]['sources'][0]['url']
        item['summary'] = playlist['description']
        item['_playlist'] = []
        tracks_html = '<details><summary style="font-weight:bold;">Tracks:</summary>'
        for it in playlist['content']['items']:
            track = it['itemV2']['data']
            track_id = track['uri'].split(':')[-1]
            artists = []
            for artist in track['artists']['items']:
                artist_url = 'https://open.spotify.com/artist/' + artist['uri'].split(':')[-1]
                artists.append('<a href="{}">{}</a>'.format(artist_url, artist['profile']['name']))
            artist = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(artists))
            playback_url = get_ytmusic_audio(track)
            if playback_url:
                playback_url = config.server + '/audio?url=' + quote_plus(playback_url)
            else:
                playback_url = 'https://open.spotify.com/embed/track/' + track['uri'].split(':')[-1]
            tracks_html += utils.add_audio_v2(playback_url, track['albumOfTrack']['coverArt']['sources'][0]['url'], track['name'], 'https://open.spotify.com/track/' + track_id, artist, '', '', -1, 'audio_link', small_poster=True, border=False, margin='1em auto 1em auto')
            item['_playlist'].append({
                "src": playback_url + '&novideojs',
                "name": track['name'],
                "artist": re.sub(r'<a [^>]+>|</a>', '', artist),
                "image": item['image']
            })
        tracks_html += '</details>'
        playback_url = config.server + '/playlist?url=' + quote_plus(item['url'])
        if '_display_date' in item:
            display_date = 'Updated: ' + item['_display_date']
        else:
            display_date = ''
        item['content_html'] = utils.add_audio_v2(playback_url, item['image'], item['title'], item['url'], item['author']['name'], item['author']['url'], display_date, -1, desc=tracks_html)

    elif content_type == 'show':
        m = re.search(r'"queryShowMetadataV2","query","([^"]+)', web_player_js)
        if not m:
            logger.warning('unable to find queryShowMetadataV2 persistedQuery hash')
            return None
        post_data = {
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": m.group(1)
                }
            },
            "operationName": "queryShowMetadataV2",
            "variables": {
                "uri": "spotify:show:" + content_id    
            }
        }
        r = curl_cffi.post('https://api-partner.spotify.com/pathfinder/v2/query', json=post_data, headers=headers, impersonate='chrome', proxies=config.proxies )
        if r.status_code != 200:
            logger.warning('unable to get queryShowMetadataV2 data')
            return None
        show = r.json()['data']['podcastUnionV2']
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
        image = utils.closest_dict(show['coverArt']['sources'], 'width', 640)
        item['image'] = image['url']
        item['summary'] = show['htmlDescription']
        episodes_html = ''
        if 'embed' not in args and '/embed/' not in url:
            if item['summary'].startswith('<'):
                episodes_html += item['summary']
            else:
                episodes_html += '<p>' + item['summary'] + '</p>'
        m = re.search(r'"queryPodcastEpisodes","query","([^"]+)', web_player_js)
        if m:
            post_data = {
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": m.group(1)
                    }
                },
                "operationName": "queryPodcastEpisodes",
                "variables": {
                    "uri": "spotify:show:" + content_id,
                    "offset": 0,
                    "limit": 10
                }
            }
            r = curl_cffi.post('https://api-partner.spotify.com/pathfinder/v2/query', json=post_data, headers=headers, impersonate='chrome', proxies=config.proxies )
            if r.status_code == 200:
                episodes = r.json()['data']['podcastUnionV2']['episodesV2']['items']
                if save_debug:
                    utils.write_file(episodes, './debug/episodes.json')
                item['_playlist'] = []
                episodes_html += '<details><summary style="font-weight:bold;">Episodes:</summary>'
                for it in episodes:
                    episode = it['entity']['data']
                    if episode['__typename'] == 'RestrictedContent':
                        continue
                    if episode.get('releaseDate'):
                        dt = datetime.fromisoformat(episode['releaseDate']['isoString'])
                        display_date = utils.format_display_date(dt, date_only=True)
                        if 'date_published' not in item:
                            item['date_published'] = dt.isoformat()
                            item['_timestamp'] = dt.timestamp()
                            item['_display_date'] = utils.format_display_date(dt)
                    else:
                        display_date = ''
                    playback_url = 'https://open.spotify.com/embed/' + '/'.join(episode['uri'].split(':')[1:])
                    episodes_html += utils.add_audio_v2(playback_url, '', episode['name'], utils.clean_url(episode['sharingInfo']['shareUrl']), '', '', display_date, episode['duration']['totalMilliseconds'] / 1000, audio_type='audio_redirect', show_poster=False, border=False, margin='1em auto 1em auto')
                    item['_playlist'].append({
                        "src": config.server + '/audio?url=' + quote_plus(playback_url),
                        "name": episode['name'],
                        "artist": item['author']['name'],
                        "image": item['image']
                    })
                episodes_html += '</details>'
            else:
                logger.warning('unable to get queryPodcastEpisodes data')
            playback_url = config.server + '/playlist?url=' + quote_plus(item['url'])
            item['content_html'] = utils.add_audio_v2(playback_url, item['image'], item['title'], item['url'], item['author']['name'], '', '', -1, audio_type='audio_link', desc=episodes_html)
        else:
            logger.warning('unable to find queryPodcastEpisodes persistedQuery hash')
            item['content_html'] = utils.add_audio_v2('', item['image'], item['title'], item['url'], item['author']['name'], '', '', -1, desc=episodes_html)

    elif content_type == 'episode':
        m = re.search(r'"getEpisodeOrChapter","query","([^"]+)', web_player_js)
        if not m:
            logger.warning('unable to find getEpisodeOrChapter persistedQuery hash')
            return None
        post_data = {
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": m.group(1)
                }
            },
            "operationName": "getEpisodeOrChapter",
            "variables": {
                "uri": "spotify:episode:" + content_id
            }
        }
        r = curl_cffi.post('https://api-partner.spotify.com/pathfinder/v2/query', json=post_data, headers=headers, impersonate='chrome', proxies=config.proxies )
        if r.status_code != 200:
            logger.warning('unable to get getEpisodeOrChapter data')
            return None
        episode = r.json()['data']['episodeUnionV2']
        if save_debug:
            utils.write_file(episode, './debug/spotify.json')
        item['id'] = episode['uri']
        item['url'] = utils.clean_url(episode['sharingInfo']['shareUrl'])
        item['title'] = episode['name']
        if episode.get('releaseDate'):
            dt = datetime.fromisoformat(episode['releaseDate']['isoString'])
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt, date_only=True)
        item['author'] = {
            "name": episode['podcastV2']['data']['name'],
            "url": 'https://open.spotify.com/show/' + episode['podcastV2']['data']['uri'].split(':')[-1]
        }
        item['authors'] = []
        item['authors'].append(item['author'])
        item['image'] = episode['coverArt']['sources'][-1]['url']
        item['summary'] = episode['htmlDescription']
        if 'embed' not in args and '/embed/' not in url:
            if item['summary'].startswith('<'):
                desc = item['summary']
            else:
                desc = '<p>' + item['summary'] + '</p>'
        else:
            desc = ''
        playback_url = 'https://open.spotify.com/embed/episode/' + content_id
        audio_type = 'audio_link'
        widevine = utils.get_url_json('https://spclient.wg.spotify.com/soundfinder/v1/unauth/episode/' + content_id + '/com.widevine.alpha?market=US', headers=headers)
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
        item['content_html'] = utils.add_audio_v2(playback_url, item['image'], item['title'], item['url'], item['author']['name'], item['author']['url'], item['_display_date'], float(episode['duration']['totalMilliseconds']) / 1000, audio_type=audio_type, desc=desc)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return None
