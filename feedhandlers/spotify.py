import pytz, re
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_authorization_header():
    # https://open.spotify.com/get_access_token?reason=transport&productType=embed_podcast
    # Top Songs - USA
    url = 'https://open.spotify.com/playlist/37i9dQZEVXbLp5XoPON0wI'
    spotify_html = utils.get_url_html(url)
    if not spotify_html:
        return None
    # utils.write_file(spotify_html, './debug/debug.html')
    m = re.search(r'"accessToken":"([^"]+)', spotify_html)
    if not m:
        return None
    header = {}
    header['authorization'] = 'Bearer ' + m.group(1)
    return header


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

    api_url = 'https://api.spotify.com/v1/{}s/{}'.format(content_type, content_id)
    if content_type == 'album' or content_type == 'playlist':
        api_url += '/tracks'
    if content_type == 'show':
        api_url += '/episodes'
    if 'max' in args:
        api_url += '?limit={}'.format(args['max'])

    headers = get_authorization_header()
    if not headers:
        logger.warning('unable to get Spotify authorization token')
        return None

    item = {}
    if content_type == 'track':
        # https://open.spotify.com/track/4nRyBgsqXEP2oPfzaMeZr7?si=c09ed9bb1b69462b
        track_json = utils.get_url_json('https://api.spotify.com/v1/{}s/{}'.format(content_type, content_id), headers=headers)
        if not track_json:
            return None
        if save_debug:
            utils.write_file(track_json, './debug/spotify.json')

        item['id'] = track_json['id']
        item['url'] = track_json['external_urls']['spotify']
        item['title'] = track_json['name']

        dt = datetime.fromisoformat(track_json['album']['release_date'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

        artists = []
        bylines = []
        for artist in track_json['artists']:
            artists.append(artist['name'])
            bylines.append('<a href="{}">{}</a>'.format(artist['external_urls']['spotify'], artist['name']))
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(artists))
        byline = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(bylines))
        item['_image'] = track_json['album']['images'][0]['url']

        if track_json.get('preview_url'):
            poster = '<a href="{}"><img src="{}/image?url={}&width=128&overlay=audio"/></a>'.format(track_json['preview_url'], config.server, quote_plus(item['_image']))
        else:
            poster = '<a href="{}"><img src="{}/image?url={}&width=128"/></a>'.format(track_json['external_urls']['spotify'], config.server, quote_plus(item['_image']))

        item['content_html'] = '<table style="width:90%; max-width:496px; margin-left:auto; margin-right:auto;"><tr><td style="width:128px;">{}</td><td style="vertical-align:top;"><b><a href="{}">{}</a></b><br/>by {}<br/><small>from <a href="{}">{}</a></small></td></tr></table>'.format(poster, track_json['external_urls']['spotify'], track_json['name'], byline, track_json['album']['external_urls']['spotify'], track_json['album']['name'])

    elif content_type == 'album' or content_type == 'playlist':
        # https://open.spotify.com/album/5B4PYA7wNN4WdEXdIJu58a
        playlist_json = utils.get_url_json('https://api.spotify.com/v1/{}s/{}'.format(content_type, content_id), headers=headers)
        if not playlist_json:
            return None
        if save_debug:
            utils.write_file(playlist_json, './debug/spotify.json')

        item['id'] = playlist_json['id']
        item['url'] = playlist_json['external_urls']['spotify']
        item['title'] = playlist_json['name']

        dt = None
        byline = ''
        item['author'] = {}
        if content_type == 'playlist':
            item['author']['name'] = playlist_json['owner']['display_name']
            byline = '<a href="{}">{}</a>'.format(playlist_json['owner']['external_urls']['spotify'], playlist_json['owner']['display_name'])
            # Assume first track is the most recent addition
            dt = datetime.fromisoformat(playlist_json['tracks']['items'][0]['added_at'].replace('Z', '+00:00'))
        elif content_type == 'album':
            artists = []
            bylines = []
            for artist in playlist_json['artists']:
                artists.append(artist['name'])
                bylines.append('<a href="{}">{}</a>'.format(artist['external_urls']['spotify'], artist['name']))
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(artists))
            byline = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(bylines))
            dt = datetime.fromisoformat(playlist_json['release_date'])
        if dt:
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

        item['_image'] = playlist_json['images'][0]['url']

        if playlist_json.get('description'):
            item['summary'] = playlist_json['description']

        poster = '{}/image?url={}&width=128'.format(config.server, quote_plus(item['_image']))
        item['content_html'] = '<table style="width:90%; max-width:496px; margin-left:auto; margin-right:auto;"><tr><td style="width:128px;"><a href="{}"><img src="{}" style="width:128px;"/></a></td><td style="vertical-align:top;"><b><a href="{}">{}</a></b><br/>by {}</td></tr><tr><td colspan="2">Tracks:<ol style="margin-top:0;">'.format(item['url'], poster, item['url'], item['title'], byline)
        if 'max' in args and content_type == 'playlist':
            i_max = int(args['max'])
        elif 'embed' in args and content_type == 'playlist':
            i_max = 10
        else:
            i_max = -100
        for i, track_item in enumerate(playlist_json['tracks']['items']):
            if content_type == 'playlist':
                track = track_item['track']
            else:
                track = track_item
            if not track:
                i_max = i_max + 1
                continue
            if i == i_max:
                item['content_html'] += '</ol></td></tr><tr><td colspan="2" style="text-align:center;"><a href="{}/content?url={}">View full playlist</a></td></tr>'.format(config.server, quote_plus(url))
                break
            artists = []
            bylines = []
            for artist in track['artists']:
                artists.append(artist['name'])
                bylines.append('<a href="{}">{}</a>'.format(artist['external_urls']['spotify'], artist['name']))
            if content_type == 'playlist':
                item['content_html'] += '<li><a href="{}">{}</a><br/><small>by {}</small></li>'.format(track['external_urls']['spotify'], track['name'], ', '.join(bylines))
            else:
                item['content_html'] += '<li><a href="{}">{}</a>'.format(track['external_urls']['spotify'], track['name'])
        if i != i_max:
            item['content_html'] += '</ol></td></tr>'
        item['content_html'] += '</table>'

    elif content_type == 'show':
        show_json = utils.get_url_json('https://api.spotify.com/v1/shows/{}?market=US'.format(content_id), headers=headers)
        if not show_json:
            return None
        if save_debug:
            utils.write_file(show_json, './debug/spotify.json')
        item['id'] = show_json['id']
        item['url'] = show_json['external_urls']['spotify']
        item['title'] = show_json['name']
        dt = datetime.fromisoformat(show_json['episodes']['items'][0]['release_date'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
        item['author'] = {
            "name": item['title'],
            "url": item['url']
        }
        item['authors'] = []
        item['authors'].append(item['author'])
        item['image'] = show_json['images'][0]['url']
        poster = '{}/image?url={}&overlay=audio'.format(config.server, quote_plus(item['image']))
        if show_json.get('html_description'):
            item['summary'] = show_json['html_description']
        else:
            item['summary'] = '<p>' + show_json['description'] + '</p>'
        item['content_html'] = '<div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:8px; margin:8px;">'
        item['content_html'] += '<div style="flex:1; min-width:128px; max-width:160px;"><a href="{}/playlist?url={}" target="_blank"><img src="{}" style="width:100%;"/></a></div>'.format(config.server, quote_plus(item['url']), poster)
        item['content_html'] += '<div style="flex:2; min-width:256px;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(item['url'], item['title'])
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
        n = min(n, show_json['episodes']['total'])
        for episode in show_json['episodes']['items'][:n]:
            tz_loc = pytz.timezone(config.local_tz)
            dt_loc = datetime.fromisoformat(episode['release_date'])
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
            if episode.get('external_playback_url'):
                playback_url = utils.get_redirect_url(episode['external_playback_url'])
            elif episode.get('audio_preview_url'):
                playback_url = utils.get_redirect_url(episode['audio_preview_url'])
            else:
                playback_url = ''
            if playback_url:
                item['_playlist'].append({
                    "src": playback_url,
                    "name": episode['name'],
                    "artist": utils.format_display_date(dt, False),
                    "image": item['image']
                })
            item['content_html'] += utils.add_audio(playback_url, item['image'], episode['name'], episode['external_urls']['spotify'], '', '', utils.format_display_date(dt, False), float(episode['duration_ms']) / 1000, show_poster=False)
        if n < show_json['episodes']['total']:
            item['content_html'] += '<div><a href="{}">View more episodes</a></div>'.format(item['url'])

    elif content_type == 'episode':
        episode_json = utils.get_url_json('https://api.spotify.com/v1/episodes/{}?market=US'.format(content_id), headers=headers)
        if not episode_json:
            return None
        if save_debug:
            utils.write_file(episode_json, './debug/spotify.json')

        item['id'] = episode_json['id']
        item['url'] = episode_json['external_urls']['spotify']
        item['title'] = episode_json['name']
        dt = datetime.fromisoformat(episode_json['release_date'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        item['author'] = {
            "name": episode_json['show']['name'],
            "url": episode_json['show']['external_urls']['spotify']
        }
        item['authors'] = []
        item['authors'].append(item['author'])
        item['summary'] = episode_json['html_description']
        item['image'] = episode_json['images'][0]['url']
        if episode_json.get('external_playback_url'):
            playback_url = utils.get_redirect_url(episode_json['external_playback_url'])
        elif episode_json.get('audio_preview_url'):
            playback_url = utils.get_redirect_url(episode_json['audio_preview_url'])
        item['_audio'] = playback_url
        attachment = {}
        attachment['url'] = item['_audio']
        attachment['mime_type'] = 'audio/mpeg'
        item['attachments'] = []
        item['attachments'].append(attachment)
        item['content_html'] = utils.add_audio(item['_audio'], item['image'], item['title'], item['url'], item['author']['name'], item['author']['url'], item['_display_date'], float(episode_json['duration_ms']) / 1000)
        if 'embed' in args or '/embed/' in url:
            return item
        item['content_html'] += item['summary']
    return item


def get_feed(url, args, site_json, save_debug=False):
    return None
