import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, unquote_plus

import config, utils
from feedhandlers import youtube

import logging
logger = logging.getLogger(__name__)

def get_authorization_header():
  # Top Songs - USA
  url = 'https://open.spotify.com/playlist/37i9dQZEVXbLp5XoPON0wI'
  spotify_html = utils.get_url_html(url)
  m = re.search(r'"accessToken":"([^"]+)', spotify_html)
  if not m:
    return None
  header = {}
  header['authorization'] = 'Bearer ' + m.group(1)
  return header

def get_content(url, args, save_debug=False):
  m = re.search(r'https:\/\/open\.spotify\.com\/([^\/]+)\/([0-9a-zA-Z]+)', url)
  if not m:
    m = re.search(r'https:\/\/open\.spotify\.com\/embed\/([^\/]+)\/([0-9a-zA-Z]+)', url)
  if not m:
    logger.warning('unable to parse Spotify url ' + url)
    return None

  content_type = m.group(1)
  content_id = m.group(2)
  api_url = 'https://api.spotify.com/v1/{}s/{}'.format(content_type, content_id)
  if content_type == 'album' or content_type == 'playlist':
    api_url += '/tracks'
  if content_typ == 'show':
    api_url += '/episodes'
  if 'max' in args:
    api_url += '?limit=' + args['max']

  headers = get_authorization_header()
  if not headers:
    logger.warning('unable to get Spotify authorization token')
    return None
  api_json = utils.get_url_json(api_url, headers=headers)
  if not api_json:
    return None
  if save_debug:
    utils.write_file(api_json, './debug/spotify.json')


  embed_html = utils.get_url_html(url)
  if not embed_html:
    return None

  soup = BeautifulSoup(embed_html, 'html.parser')
  if '/embed/' in url:
    el = soup.find('script', id='resource')
  elif '/embed-podcast/' in url:
    el = soup.find('script', id='preloaded-state')
  if not el:
    print('no embed json found')
    return None

  embed_json = json.loads(unquote_plus(el.string))
  #if save_debug:
  #  utils.write_file(embed_json, './debug/spotify.json')

  item = {}
  if '/embed/track/' in url:
    item['id'] = embed_json['id']
    item['url'] = embed_json['external_urls']['spotify']

    query = embed_json['name']
    artists = []
    byline = []
    for artist in embed_json['artists']:
      artists.append(artist['name'])
      byline.append('<a href="{}">{}</a>'.format(artist['external_urls']['spotify'], artist['name']))
      query += ' {}'.format(artist['name'])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(artists))

    item['title'] = '{} by {}'.format(embed_json['name'], item['author']['name'])

    if embed_json['album']['album_type'] == 'single':
      dt = datetime.strptime(embed_json['album']['release_date'], '%Y-%m-%d')
      item['date_published'] = dt.isoformat()
      item['_timestamp'] = dt.timestamp()
      item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
      item['_image'] = embed_json['album']['images'][0]['url']
    else:
      logger.warning('unhandled album type {} for a track'.format(embed_json['album']['album_type']))

    #item['summary'] = embed_json['data']['entity']['description']

    item['content_html'] = '<center><table style="width:480px;"><tr><td width="30%" rowspan="3"><img style="height:8em;" src="{}"></td><td><a href="{}"><b>{}</b></a></td></tr>'.format(item['_image'], embed_json['external_urls']['spotify'], embed_json['name'])
    item['content_html'] += '<tr><td><small>from <a href="{}">{}</a><br />by {}</small></td></tr>'.format(embed_json['album']['external_urls']['spotify'], embed_json['album']['name'], ', '.join(byline))
    yt_id = youtube.search(query)
    if yt_id:
      item['_audio'] = '{}/audio?url='.format(config.server, quote_plus('https://www.youtube.com/watch?v=' + yt_id))
      item['content_html'] += '<tr><td><audio controls><source src="{}"></audio><br /><a href="https://www.youtube.com/watch?v={}"><small>Play track</small></a></td></tr></table></center>'.format(item['_audio'], yt_id)
    else:
      item['_audio'] = embed_json['preview_url']
      item['content_html'] += '<tr><td><audio controls><source src="{0}"></audio><br /><a href="{0}"><small>Play track</small></a></td></tr></table></center>'.format(item['_audio'])

  elif '/embed/playlist/' in url:
    item['id'] = embed_json['id']
    item['url'] = embed_json['external_urls']['spotify']
    item['title'] = embed_json['name']

    # Assume first track is the most recent addition
    dt = datetime.fromisoformat(embed_json['tracks']['items'][0]['added_at'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['author'] = {}
    item['author']['name'] = embed_json['owner']['display_name']

    item['_image'] = embed_json['images'][0]['url']
    item['summary'] = embed_json['description']

    poster = '{}/image?url={}&width=128'.format(config.server, quote_plus(item['_image']))
    item['content_html'] = '<center><table style="width:360px; border:1px solid black; border-radius:10px; border-spacing:0;"><tr><td style="width:1%; padding:0; margin:0; border-bottom: 1px solid black;"><a href="{}"><img style="display:block; border-top-left-radius:10px;" src="{}" /></a></td><td style="padding-left:0.5em; vertical-align:top; border-bottom: 1px solid black;"><h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by {}</small></td></tr><tr><td colspan="2">Tracks:<ol style="margin-top:0;">'.format(item['url'], poster, item['url'], item['title'], item['author']['name'])
    if 'max' in args:
      i_max = int(args['max'])
    else:
      i_max = -1
    for i, track in enumerate(embed_json['tracks']['items']):
      if i == i_max:
        item['content_html'] += '</ol></td></tr><tr><td colspan="2" style="text-align:center;"><a href="{}/content?url={}">View full playlist</a></td></tr>'.format(config.server, quote_plus(url))
        break
      artists = []
      byline = []
      for artist in track['track']['artists']:
        artists.append(artist['name'])
        byline.append('<a href="{}">{}</a>'.format(artist['external_urls']['spotify'], artist['name']))
      item['content_html'] += '<li><a href="{}">{}</a><br/><small>by {}</small></li>'.format(track['track']['external_urls']['spotify'], track['track']['name'], ', '.join(byline))
    if i != i_max:
      item['content_html'] += '</ol></td></tr>'
    item['content_html'] += '</table></center>'

  elif '/embed-podcast/' in url:
    item['id'] = embed_json['data']['entity']['id']
    item['url'] = embed_json['data']['entity']['external_urls']['spotify']
    item['title'] = embed_json['data']['entity']['name']

    dt = datetime.strptime(embed_json['data']['entity']['release_date'], '%Y-%m-%d')
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['author'] = {}
    item['author']['name'] = embed_json['data']['entity']['show']['publisher']

    item['_image'] = embed_json['data']['entity']['images'][0]['url']
    item['_audio'] = embed_json['data']['entity']['external_playback_url']

    item['summary'] = embed_json['data']['entity']['description']

    item['content_html'] = '<center><table style="width:480px;"><tr><td width="30%" rowspan="3"><img width="100%" src="{}"></td><td><a href="{}"><b>{}</b></a></td></tr><tr><td><small>'.format(item['_image'], item['url'], item['title'])
    item['content_html'] += '<a href="{}">{}</a></small></td></tr>'.format(embed_json['data']['entity']['show']['external_urls']['spotify'], embed_json['data']['entity']['show']['name'])
    item['content_html'] += '<tr><td><audio controls><source src="{0}" type="audio/mpeg"><a href="{0}">Play track</a></audio></td></tr></table></center>'.format(item['_audio'])
    item['content_html'] += '<p>{}</p>'.format(item['summary'])

  return item

def get_feed(args, save_debug=False):
  return None