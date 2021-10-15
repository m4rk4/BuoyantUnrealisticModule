import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging
logger = logging.getLogger(__name__)

def get_soundcloud_key():
  pf = utils.get_url_html('https://www.pitchfork.com')
  if pf:
    soup = BeautifulSoup(pf, 'html.parser')
    for script in soup.find_all('script', attrs={"src": True}):
      if re.search(r'main-[0-9a-fA-F]+\.js', script['src']):
        script_js = utils.get_url_html('https://www.pitchfork.com' + script['src'])
        if script_js:
          m = re.search(r'soundcloudKey:"([^"]+)"', script_js)
          if m:
            return m.group(1)
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
  json_url = 'https://api-v2.soundcloud.com/playlists/{}?client_id={}'.format(track_id, client_id)
  if secret_token:
    json_url += '&secret_token=' + secret_token
  playlist_json = utils.get_url_json(json_url)
  if not playlist_json:
    return None

  if save_debug:
    with open('./debug/debug.json', 'w') as file:
      json.dump(playlist_json, file, indent=4)

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
      #item['content_html'] += '<tr><td><audio id="track{0}" src="{1}"></audio><div><button onclick="audio=document.getElementById(\'track{0}\'); img=document.getElementById(\'icon{0}\'); if (audio.paused) {{audio.play(); img.src=\'/static/play-icon.png\'}} else {{audio.pause(); img.src=\'/static/pause-icon.png\'}}" style="border:none;"><img id="icon{0}" src="/static/pause-icon.png" style="height:64px; background-image:url(\'{2}\');" /></button></div></td>'.format(i, audio_url, poster)
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

def get_content(url, args, save_debug):
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

def get_feed(args, save_debug):
  return None