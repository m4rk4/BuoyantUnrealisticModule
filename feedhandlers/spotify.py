import math, re
from datetime import datetime
from urllib.parse import quote_plus

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


def get_content(url, args, save_debug=False):
    m = re.search(r'https://open\.spotify\.com/embed(-legacy)?/([^/]+)/([0-9a-zA-Z]+)', url)
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
        else:
            i_max = -1
        for i, track_item in enumerate(playlist_json['tracks']['items']):
            if content_type == 'playlist':
                track = track_item['track']
            else:
                track = track_item
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

        item['author'] = {}
        item['author']['name'] = show_json['publisher']

        item['_image'] = show_json['images'][0]['url']
        # item['_audio'] = show_json['external_playback_url']

        item['summary'] = show_json['description']

        poster = '{}/image?url={}&width=128'.format(config.server, quote_plus(item['_image']))
        item['content_html'] = '<center><table style="width:360px; border:1px solid black; border-radius:10px; border-spacing:0;"><tr><td style="width:1%; padding:0; margin:0; border-bottom: 1px solid black;"><a href="{}"><img style="display:block; border-top-left-radius:10px;" src="{}" /></a></td><td style="padding-left:0.5em; vertical-align:top; border-bottom: 1px solid black;"><h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by {}</small></td></tr><tr><td colspan="2">Episodes:<ol style="margin-top:0;">'.format(item['url'], poster, item['url'], item['title'], item['author']['name'])
        if 'max' in args:
            i_max = int(args['max'])
        else:
            i_max = -1
        for i, episode in enumerate(show_json['episodes']['items']):
            if i == i_max:
                item['content_html'] += '</ol></td></tr><tr><td colspan="2" style="text-align:center;"><a href="{}/content?url={}">View all episodes</a></td></tr>'.format(config.server, quote_plus(url))
                break
            minutes = math.ceil(episode['duration_ms'] / 1000 / 60)
            if episode.get('external_playback_url'):
                playback_url = utils.get_redirect_url(episode['external_playback_url'])
                item['content_html'] += '<li><a href="{}">{}</a><br/><small>{} &ndash; {} min</small></li>'.format(playback_url, episode['name'], episode['release_date'], minutes)
            else:
                item['content_html'] += '<li>{}<br/><small>{} &ndash; {} min</small></li>'.format(episode['name'], episode['release_date'], minutes)
        if i != i_max:
            item['content_html'] += '</ol></td></tr>'
        item['content_html'] += '</table></center>'

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
        item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

        item['author'] = {}
        item['author']['name'] = episode_json['show']['publisher']

        item['summary'] = episode_json['html_description']
        item['_image'] = episode_json['images'][0]['url']
        if episode_json.get('external_playback_url'):
            playback_url = utils.get_redirect_url(episode_json['external_playback_url'])
        elif episode_json.get('audio_preview_url'):
            playback_url = utils.get_redirect_url(episode_json['audio_preview_url'])
        item['_audio'] = playback_url

        # minutes = math.ceil(episode_json['duration_ms'] / 1000 / 60)
        duration = []
        t = math.floor(float(episode_json['duration_ms']) / 3600000)
        if t >= 1:
            duration.append('{} hr'.format(t))
        t = math.ceil((float(episode_json['duration_ms']) - 3600000 * t) / 60)
        if t > 0:
            duration.append('{} min.'.format(t))

        poster = '{}/image?url={}&width=128&overlay=audio'.format(config.server, quote_plus(item['_image']))
        desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small><a href="{}">{}</a><br/>by {}</small>'.format(
            item['url'], item['title'], episode_json['show']['external_urls']['spotify'], episode_json['show']['name'],
            item['author']['name'], ', '.join(duration))
        item['content_html'] = '<div><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><div>{}</div><div style="clear:left;"><blockquote><small>{}</small></blockquote></div>'.format(item['_audio'], poster, desc, item['summary'])
    return item


def get_feed(args, save_debug=False):
    return None
