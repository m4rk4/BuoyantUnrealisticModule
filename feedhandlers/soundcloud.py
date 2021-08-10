import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus

import utils

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
  if url.startswith('https://w.soundcloud.com/player/'):
    el = soup.find('link', rel='canonical')
    if el:
      sc_html = utils.get_url_html(el['href'])
      if not sc_html:
        return None
      soup = BeautifulSoup(sc_html, 'html.parser')

  track = ''
  playlist = ''
  el = soup.find('meta', attrs={"property": "al:ios:url"})
  # <meta property="al:ios:url" content="soundcloud://sounds:1056424066">
  # <meta property="al:ios:url" content="soundcloud://playlists:1265306068">
  if el:
    m = re.search(r'soundcloud:\/\/sounds:(\d+)', el['content'])
    if m:
      track = m.group(1)
    else:
      m = re.search(r'soundcloud:\/\/playlists:(\d+)', el['content'])
      if m:
        playlist = m.group(1)

  audio_json = None
  if track:
    audio_json = utils.get_url_json('https://api.soundcloud.com/tracks/{}.json?consumer_key={}'.format(track, sc_key))
  elif playlist:
    audio_json = utils.get_url_json('https://api.soundcloud.com/playlists/{}.json?consumer_key={}'.format(playlist, sc_key))

  if audio_json:
    if save_debug:
      with open('./debug/debug.json', 'w') as file:
        json.dump(audio_json, file, indent=4)

    item = {}
    item['id'] = audio_json['id']
    item['url'] = audio_json['permalink_url']
    item['title'] = audio_json['title']

    # 2021/05/27 04:41:57 +0000
    dt = datetime.strptime(audio_json['created_at'], '%Y/%m/%d %H:%M:%S +0000').replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    if audio_json.get('last_modified'):
      dt = datetime.strptime(audio_json['last_modified'], '%Y/%m/%d %H:%M:%S +0000').replace(tzinfo=timezone.utc)
      item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if audio_json['user'].get('full_name'):
      item['author']['name'] = audio_json['user']['full_name']
    else:
      item['author']['name'] = audio_json['user']['username']

    item['tags'] = []
    item['tags'].append(audio_json['genre'])

    item['_image'] = audio_json['artwork_url']

    redirect_url = 'https://buoyantunrealisticmodule.m4rk4.repl.co/redirect?&url=' + quote_plus(audio_json['permalink_url'])

    if audio_json.get('tracks'):
      item['content_html'] = '<center><table style="width:480px;"><tr><td colspan="2"><img width="100%" src="{}"></td></tr>'.format(audio_json['artwork_url'])
      for i, track in enumerate(audio_json['tracks']):
        if track['duration'] <= 30000:
          # Skip - this is likely a 30 sec sample
          item['content_html'] += '<tr><td colspan="2" style="width:50%; height:3em;">{0}.&nbsp;<a href="{1}">{2}</a></td><td>'.format(i+1, track['permalink_url'], track['title'])
        else:          
          redirect_url = 'https://buoyantunrealisticmodule.m4rk4.repl.co/redirect?&url=' + quote_plus(track['permalink_url'])
          item['content_html'] += '<tr><td style="width:50%; height:3em;">{0}.&nbsp;<a href="{1}">{2}</a></td><td><audio controls><source src="{3}" type="audio/mpeg"><a href="{3}">Play track</a></audio></td></tr>'.format(i+1, track['permalink_url'], track['title'], redirect_url)
      item['content_html'] += '</table></center>'

    else:
      item['_audio'] = audio_json['stream_url'] + '?consumer_key=' + sc_key

      item['content_html'] = '<center><table style="width:480px;"><tr><td width="30%" rowspan="3"><img width="100%" src="{}"></td><td><a href="{}"><b>{}</b></a></td></tr><tr><td><small>'.format(audio_json['artwork_url'], audio_json['permalink_url'], audio_json['title'])
      item['content_html'] += 'by <a href="{}">{}</a></small></td></tr>'.format(audio_json['user']['permalink_url'], item['author']['name'])
      item['content_html'] += '<tr><td><audio controls><source src="{0}" type="audio/mpeg"><a href="{0}">Play track</a></audio></td></tr></table></center>'.format(redirect_url)

  return item

def get_feed(args, save_debug):
  return None