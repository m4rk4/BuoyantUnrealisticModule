import math, re, requests
from datetime import datetime
from urllib.parse import quote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)

# Apple Music API documentation
# https://developer.apple.com/documentation/applemusicapi/

def get_token():
    js = utils.get_url_html('https://embed.podcasts.apple.com/build/web-embed.esm.js')
    if not js:
        return ''
    for it in re.findall(r'\bp-[0-9a-f]+', js):
        js = utils.get_url_html('https://embed.podcasts.apple.com/build/{}.entry.js'.format(it))
        if js:
            m = re.search(r'="(ey[^"]+)"', js)
            if m:
                return m.group(1)
    logger.warning('Apple podcast token not found')
    return ''


def get_apple_data(api_url, url, save_debug=False):
    s = requests.Session()
    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.9",
        "access-control-request-headers": "authorization",
        "access-control-request-method": "GET",
        "cache-control": "no-cache",
        "dnt": "1",
        "origin": "https://embed.podcasts.apple.com",
        "pragma": "no-cache",
        "referer": "https://embed.podcasts.apple.com/",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "sec-gpc": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.5005.124 Safari/537.36 Edg/102.0.1245.44"
    }
    preflight = s.options(api_url, headers=headers)
    if preflight.status_code != 204:
        logger.warning('unexpected status code {} getting preflight info from {}'.format(preflight.status_code, url))
        return ''

    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "dnt": "1",
        "origin": "https://embed.podcasts.apple.com",
        "pragma": "no-cache",
        "referer": "https://embed.podcasts.apple.com/",
        "sec-ch-ua": "\" Not A;Brand\";v=\"99\", \"Chromium\";v=\"102\", \"Microsoft Edge\";v=\"102\"",
        "sec-ch-ua-mobile": "?0",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "sec-gpc": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.5005.124 Safari/537.36 Edg/102.0.1245.44"
    }

    sites_json = utils.read_json_file('./sites.json')
    headers['authorization'] = 'Bearer ' + sites_json['apple']['token']
    new_token = ''

    r = s.get(api_url, headers=headers)
    if r.status_code != 200:
        # The token might be expired, try to get a new one
        new_token = get_token()
        if new_token:
            logger.debug('trying new Apple token to ' + new_token)
            headers['authorization'] = 'Bearer ' + new_token
            r = s.get(api_url, headers=headers)

    if r.status_code != 200:
        logger.warning('unexpected status code {} getting request info from {}'.format(r.status_code, url))
        return ''

    if new_token:
        sites_json['apple']['token'] = new_token
        utils.write_file(sites_json, './sites.json')
    return r.json()


def get_album_track(track):
    item = {}
    item['id'] = track['id']
    item['url'] = track['attributes']['url']
    item['title'] = track['attributes']['name']

    if track['attributes'].get('releaseDate'):
        dt = datetime.fromisoformat(track['attributes']['releaseDate'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
        item['_year'] = dt.year

    item['author'] = {}
    item['author']['name'] = track['attributes']['artistName']

    item['_album'] = {}
    item['_album']['name'] = track['attributes']['albumName']
    item['_album']['url'] = track['attributes']['url'].split('?')[0]

    if track['attributes'].get('genreNames'):
        item['tags'] = track['attributes']['genreNames']

    item['_image'] = track['attributes']['artwork']['url']

    if track['attributes'].get('durationInMillis'):
        ms = float(track['attributes']['durationInMillis'])
        m = math.floor((ms / 1000) / 60)
        s = math.floor((ms / 1000) % 60)
        item['_duration'] = '{}:{}'.format(m, s)
    else:
        item['_duration'] = 'N/A'
    return item


def get_album(url, args, site_json, save_debug=False):
    m = re.search(r'/album/[^/]+/(\d+)', url)
    if not m:
        logger.warning('unable to get album id from ' + url)
        return None
    api_url = 'https://api.music.apple.com/v1/catalog/us/albums/{}?include=artists'.format(m.group(1))
    api_json = get_apple_data(api_url, url, save_debug)
    if not api_json:

        return None
    if save_debug:
        utils.write_file(api_json, './debug/album.json')

    album = api_json['data'][0]

    track_id = ''
    m = re.search(r'\bi=(\d+)', url)
    if m:
        track_id = m.group(1)

    item = {}
    if track_id:
        for track in album['relationships']['tracks']['data']:
            if track['id'] == track_id:
                item = get_album_track(track)
                poster = item['_image'].replace('{w}', '128').replace('{h}', '128').replace('{f}', 'jpg')
                desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by {}<br/>from <a href="{}">{}</a><br/>{} &#8226; {}<br/>{}</small>'.format(item['url'], item['title'], item['author']['name'], item['_album']['url'], item['_album']['name'], item['tags'][0], item['_year'], item['_duration'])
                item['content_html'] = '<div><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><div style="overflow:hidden;">{}</div><div style="clear:left;"></div></div>'.format(item['url'], poster, desc)
                return item
    else:
        item['id'] = album['id']
        item['url'] = album['attributes']['url']
        item['title'] = album['attributes']['name']

        dt = datetime.fromisoformat(album['attributes']['releaseDate'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
        item['_year'] = dt.year

        item['author'] = {}
        item['author']['name'] = album['attributes']['artistName']
        item['author']['url'] = 'https://music.apple.com/us/artist/' + album['relationships']['artists']['data'][0]['id']

        if album['attributes'].get('genreNames'):
            item['tags'] = album['attributes']['genreNames'].copy()

        item['_image'] = album['attributes']['artwork']['url'].replace('{w}', '640').replace('{h}', '640').replace('{f}', 'jpg')

        if album['attributes'].get('description'):
            item['summary'] = album['attributes']['description']['standard']
        elif album['attributes'].get('editorialNotes'):
            if album['attributes']['editorialNotes'].get('standard'):
                item['summary'] = album['attributes']['editorialNotes']['standard']
            elif album['attributes']['editorialNotes'].get('short'):
                item['summary'] = album['attributes']['editorialNotes']['short']

        poster = album['attributes']['artwork']['url'].replace('{w}', '128').replace('{h}', '128').replace('{f}', 'jpg')
        desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by <a href="{}">{}</a><br/>{} &#8226; {}</small>'.format(item['url'], item['title'], album['attributes']['url'], item['author']['name'], item['tags'][0], item['_year'])
        item['content_html'] = '<div><img style="float:left; margin-right:8px;" src="{}"/><div>{}</div><div style="clear:left;"></div></div>'.format(poster, desc)

        item['content_html'] += '<blockquote style="border-left:3px solid #ccc; margin-top:4px; margin-left:1.5em; padding-left:0.5em;"><div style="font-weight:bold;">Tracks:</div>'
        if album['relationships']['tracks']['data'][0]['attributes']['discNumber'] != album['relationships']['tracks']['data'][-1]['attributes']['discNumber']:
            d = album['relationships']['tracks']['data'][0]['attributes']['discNumber']
            item['content_html'] += '<div>Disc {}</div>'.format(d)
        else:
            d = 99
        item['content_html'] += '<ol style="margin-top:0;">'
        for i, track in enumerate(album['relationships']['tracks']['data']):
            if track['attributes']['discNumber'] > d:
                d = track['attributes']['discNumber']
                item['content_html'] += '</ol><div>Disc {}</div><ol style="margin-top:0;">'.format(d)
            track_item = get_album_track(track)
            item['content_html'] += '<li><a href="{}">{}</a>'.format(track_item['url'], track_item['title'])
            if item['author']['name'] != track_item['author']['name']:
                item['content_html'] += ' by {}'.format(track_item['author']['name'])
            item['content_html'] += '</li>'
        item['content_html'] += '</ol></blockquote>'

        if not 'embed' in args and item.get('summary'):
            item['content_html'] += '<div>{}</div>'.format(item['summary'].replace('\n', '<br/>'))
    return item


def get_playlist(url, args, site_json, save_debug=False):
    m = re.search(r'/(pl\.[0-9a-f]+)', url)
    if not m:
        logger.warning('unable to get album id from ' + url)
        return None
    api_json = get_apple_data('https://api.music.apple.com/v1/catalog/us/playlists/{}?include=curator'.format(m.group(1)), url, save_debug)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/playlist.json')

    playlist = api_json['data'][0]

    item = {}
    item['id'] = playlist['id']
    item['url'] = playlist['attributes']['url']
    item['title'] = playlist['attributes']['name']

    dt = datetime.fromisoformat(playlist['attributes']['lastModifiedDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['author'] = {}
    item['author']['name'] = playlist['relationships']['curator']['data'][0]['attributes']['name']
    item['author']['url'] = playlist['relationships']['curator']['data'][0]['attributes']['url']

    if playlist['attributes'].get('genreNames'):
        item['tags'] = playlist['attributes']['genreNames'].copy()

    item['_image'] = playlist['attributes']['artwork']['url'].replace('{w}', '640').replace('{h}', '640').replace('{f}', 'jpg')

    if playlist['attributes'].get('description') and playlist['attributes']['description'].get('standard'):
        item['summary'] = playlist['attributes']['description']['standard']

    poster = playlist['attributes']['artwork']['url'].replace('{w}', '128').replace('{h}', '128').replace('{f}', 'jpg')
    desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by <a href="{}">{}</a></small>'.format(item['url'], item['title'], playlist['attributes']['url'], item['author']['name'])
    item['content_html'] = '<div><img style="float:left; margin-right:8px;" src="{}"/><div>{}</div><div style="clear:left;"></div></div>'.format(poster, desc)
    item['content_html'] += '<blockquote style="border-left:3px solid #ccc; margin-top:4px; margin-left:1.5em; padding-left:0.5em;"><h4 style="margin-top:0; margin-bottom:1em;">Tracks:</h4><ol style="margin-top:0;">'

    if  'embed' in args:
        n = 10
    else:
        n = -1

    for i, track in enumerate(playlist['relationships']['tracks']['data']):
        if i == n:
            break
        track_item = get_album_track(track)
        item['content_html'] += '<li><a href="{}">{}</a> by {}</li>'.format(track_item['url'], track_item['title'], track_item['author']['name'])
    item['content_html'] += '</ol></blockquote>'
    return item


def get_podcast_episode(episode):
    item = {}
    item['id'] = episode['id']
    item['url'] = episode['attributes']['url']
    item['title'] = episode['attributes']['name']

    dt = datetime.fromisoformat(episode['attributes']['releaseDateTime'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, date_only=True)

    item['author'] = {
        "name": episode['attributes']['artistName']
    }

    item['tags'] = []
    if episode['attributes'].get('genreNames'):
        item['tags'] += episode['attributes']['genreNames'].copy()
    if episode['attributes'].get('topics'):
        item['tags'] += episode['attributes']['topics'].copy()
    if not item.get('tags'):
        del item['tags']

    item['image'] = episode['attributes']['artwork']['url'].replace('{w}', '160').replace('{h}', '160').replace('{f}', 'jpg')
    item['_audio'] = utils.get_redirect_url(episode['attributes']['assetUrl'])
    item['_duration'] = utils.calc_duration(float(episode['attributes']['durationInMilliseconds']) / 1000)
    item['summary'] = episode['attributes']['description']['standard'].replace('\n', '<br/>')
    return item


def get_podcast(url, args, site_json, save_debug):
    m = re.search(r'/id(\d+)', url)
    if not m:
        logger.warning('unable to parse podcast id in ' + url)
        return None
    api_url = 'https://amp-api.podcasts.apple.com/v1/catalog/us/podcasts/{}?include=episodes'.format(m.group(1))

    m = re.search(r'\bi=(\d+)', url)
    if m:
        episode_id = m.group(1)
    else:
        episode_id = ''

    api_json = get_apple_data(api_url, url, save_debug)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/podcast.json')

    show = api_json['data'][0]

    if episode_id:
        for episode in show['relationships']['episodes']['data']:
            if episode['id'] == episode_id:
                break
    else:
        # Should be the most recent episode
        episode = show['relationships']['episodes']['data'][0]

    item = get_podcast_episode(episode)
    if episode_id:
        item['content_html'] = utils.add_audio_v2(item['_audio'], item['image'], item['title'], item['url'], show['attributes']['name'], show['attributes']['url'], item['_display_date'], item['_duration'])
        if 'summary' in item and 'embed' not in args:
            item['content_html'] += '<div>{}</div>'.format(item['summary'].replace('\n', '<br/>'))
    else:
        item = {}
        item['id'] = show['id']
        item['url'] = show['attributes']['url']
        item['title'] = show['attributes']['name']
        item['author'] = {
            "name": show['attributes']['artistName']
        }
        item['_timestamp'] = 0
        item['tags'] = show['attributes']['genreNames'].copy()
        item['image'] = show['attributes']['artwork']['url'].replace('{w}', '160').replace('{h}', '160').replace('{f}', 'jpg')
        if show['attributes'].get('description'):
            item['summary'] = show['attributes']['description']['standard'].replace('\n', '<br/>')
        elif show['attributes'].get('editorialNotes'):
            item['summary'] = show['attributes']['editorialNotes']['standard'].replace('\n', '<br/>')

        card_image = '<a href="{}" target="_blank"><div style="width:100%; height:100%; background:url(\'{}\'); background-position:center; background-size:cover; border-radius:10px 0 0 0;"></div></a>'.format(item['url'], item['image'])

        card_content = '<div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(item['url'], item['title'])
        card_content += '<div style="margin-top:8px;">' + item['author']['name'] + '</div>'

        card_footer = ''
        if 'embed' not in args and 'summary' in item:
            card_footer += '<p>' + item['summary'] + '</p>'

        # Max number of episodes to display. All episodes are added to _playlist
        if 'max' in args:
            n_max = int(args['max'])
        elif 'embed' in args:
            n_max = 3
        else:
            n_max = 10
        n_max = min(n_max, len(show['relationships']['episodes']['data']))

        item['_playlist'] = []
        card_footer += '<h3>Episodes:</h3>'
        for i, ep in enumerate(show['relationships']['episodes']['data']):
            episode = get_podcast_episode(ep)
            if episode['_timestamp'] > item['_timestamp']:
                item['date_published'] = episode['date_published']
                item['_timestamp'] = episode['_timestamp']
                item['_display_date'] = episode['_display_date']
            item['_playlist'].append({
                "src": episode['_audio'],
                "name": episode['title'],
                "artist": episode['_display_date'],
                "image": episode['image']
            })
            if i < n_max:
                card_footer += utils.add_audio_v2(episode['_audio'], episode['image'], episode['title'], episode['url'], '', '', episode['_display_date'], episode['_duration'], show_poster=False, border=False)
        if n_max < len(show['relationships']['episodes']['data']):
            card_footer += '<div><a href="{}">View more episodes</a></div>'.format(item['url'])
        item['content_html'] = utils.format_small_card(card_image, card_content, card_footer)
    return item


def get_content(url, args, site_json, save_debug=False):
    if '/podcast' in url:
        return get_podcast(url, args, site_json, save_debug)

    if '/album' in url:
        return get_album(url, args, site_json, save_debug)

    if '/playlist/' in url or '/album' in url:
        return get_playlist(url, args, site_json, save_debug)

    logger.warning('unhandled Apple url ' + url)
    return None


def get_feed(url, args, site_json, save_debug=False):
    return None
