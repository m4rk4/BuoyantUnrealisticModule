import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, unquote_plus

from feedhandlers import youtube
import utils

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
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
  if save_debug:
    utils.write_file(embed_json, './debug/spotify.json')

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
      item['_audio'] = 'https://buoyantunrealisticmodule.m4rk4.repl.co/audio?url=' + quote_plus('https://www.youtube.com/watch?v=' + yt_id)
      item['content_html'] += '<tr><td><audio controls><source src="{}"></audio><br /><a href="https://www.youtube.com/watch?v={}"><small>Play track</small></a></td></tr></table></center>'.format(item['_audio'], yt_id)
    else:
      item['_audio'] = embed_json['preview_url']
      item['content_html'] += '<tr><td><audio controls><source src="{0}"></audio><br /><a href="{0}"><small>Play track</small></a></td></tr></table></center>'.format(item['_audio'])

  elif '/embed/playlist/' in url:
    item['id'] = embed_json['id']
    item['url'] = embed_json['external_urls']['spotify']
    item['title'] = embed_json['name']

    item['author'] = {}
    item['author']['name'] = embed_json['owner']['display_name']

    item['_image'] = embed_json['images'][0]['url']
    item['summary'] = embed_json['description']

    newest_dt = datetime(2000, 1, 1)
    item['content_html'] = '<center><table style="width:640px;"><tr><td colspan="3"><img width="100%" src="{}"></td></tr>'.format(item['_image'])
    for i, track in enumerate(embed_json['tracks']['items']):
      if i == 5 and args and 'embed' in args:
        item['content_html'] += '<tr><td colspan="3" style="text-align: center;"><a href="https://buoyantunrealisticmodule.m4rk4.repl.co/content?url={}">View full playlist</a></td></tr>'.format(quote_plus(url))
        break

      query = track['track']['name']

      dt = datetime.fromisoformat(track['added_at'].replace('Z', '+00:00'))
      if newest_dt.timestamp() < dt.timestamp():
        newest_dt = dt

      artists = []
      for artist in track['track']['artists']:
        artists.append('<a href="{}">{}</a>'.format(artist['external_urls']['spotify'], artist['name']))
        query += ' {}'.format(artist['name'])
      byline = ', '.join(artists)

      item['content_html'] += '<tr style="vertical-align:top;"><td>{}.</td><td style="width:50%; height:3em;"><a href="{}">{}</a><br /><small> by {}'.format(i+1, track['track']['external_urls']['spotify'], track['track']['name'], byline)
      if track['track'].get('album'):
        item['content_html'] += '<br />from <a href="{}">{}</a>'.format(track['track']['album']['external_urls']['spotify'], track['track']['album']['name'])

      yt_id = youtube.search(query)
      if yt_id:
        yt_stream = 'https://buoyantunrealisticmodule.m4rk4.repl.co/audio?url=' + quote_plus('https://www.youtube.com/watch?v=' + yt_id)
        item['content_html'] += '</small></td><td><audio controls><source src="{}" type="audio/mpeg"></audio><br /><a href="https://www.youtube.com/watch?v={}"><small>Play track</small></a></td></tr>'.format(yt_stream, yt_id)
      else:
        item['content_html'] += '</small></td><td><audio controls><source src="{0}" type="audio/mpeg"></audio><br /><a href="{0}"><small>Play track</small></a></td></tr>'.format(track['track']['preview_url'])
    item['content_html'] += '</table></center>'

    item['date_published'] = newest_dt.isoformat()
    item['_timestamp'] = newest_dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(newest_dt.strftime('%b'), dt.day, dt.year)

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