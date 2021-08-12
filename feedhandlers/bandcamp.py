import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, unquote_plus

import utils

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
  item = None
  bc_html = utils.get_url_html(url)
  if bc_html:
    soup = BeautifulSoup(bc_html, 'html.parser')
    if 'EmbeddedPlayer' in url:
      el = soup.find('script', attrs={"data-player-data": True})
      if el:
        audio_json = json.loads(unquote_plus(el['data-player-data']))
        if save_debug:
          utils.write_file(audio_json, './debug/debug.json')
        # Render just the track
        m = re.search(r'track=(\d+)', url)
        if m:
          for track in audio_json['tracks']:
            if track['id'] == int(m.group(1)):
              return get_content(track['title_link'], args, save_debug)
      # Fallback
      el = soup.find('input', id='shareurl')
      if el:
        return get_content(el['value'], args, save_debug)

    elif '/track/' in url or '/album/' in url:
      ld_json = soup.find('script', attrs={"type": "application/ld+json"})
      if ld_json:
        audio_json = json.loads(str(ld_json.contents[0]))
        if save_debug:
          utils.write_file(audio_json, './debug/debug.json')

        item = {}
        item['id'] = audio_json['@id']
        item['url'] = url
        item['title'] = '{} — {}'.format(audio_json['name'], audio_json['byArtist']['name'])
        
        # 09 Jul 2021 00:00:00 GMT
        dt = datetime.strptime(audio_json['datePublished'], '%d %b %Y %H:%M:%S %Z').replace(tzinfo=timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
        dt = datetime.strptime(audio_json['dateModified'], '%d %b %Y %H:%M:%S %Z').replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

        item['author'] = {}
        item['author']['name'] = audio_json['byArtist']['name']
        item['tags'] = audio_json['keywords'].copy()
        item['_image'] = audio_json['image']
        poster = 'https://buoyantunrealisticmodule.m4rk4.repl.co/image?width=128&url=' + quote_plus(audio_json['image'])

        if audio_json.get('description'):
          item['summary'] = audio_json['description']
        elif audio_json['publisher'].get('description'):
          item['summary'] = audio_json['publisher']['description']

        if audio_json['@type'] == 'MusicRecording':
          if audio_json.get('additionalProperty'):
            for prop in audio_json['additionalProperty']:
              if 'mp3' in prop['name']:
                item['_audio'] = prop['value']
                break
          audio_url = 'https://buoyantunrealisticmodule.m4rk4.repl.co/audio?url=' + quote_plus(audio_json['@id'])
          item['content_html'] = '<center><table style="width:480px;"><tr><td width="30%" rowspan="3"><img width="100%" src="{}"></td><td><a href="{}"><b>{}</b></a></td></tr><tr><td><small>'.format(poster, audio_json['@id'], audio_json['name'])
          if audio_json.get('inAlbum'):
            item['content_html'] += 'from <a href="{}">{}</a><br />'.format(audio_json['inAlbum']['@id'], audio_json['inAlbum']['name'])
          item['content_html'] += 'by <a href="{}">{}</a></small></td></tr>'.format(audio_json['byArtist']['@id'], audio_json['byArtist']['name'])
          item['content_html'] += '<tr><td><audio controls><source src="{0}" type="audio/mpeg"><a href="{0}">Play track</a></audio></td></tr></table></center>'.format(audio_url)

        elif audio_json['@type'] == 'MusicAlbum':
          item['content_html'] = '<center><table style="width:480px;"><tr><td colspan="2"><img width="100%" src="{}"></td></tr>'.format(audio_json['image'])
          for i, track in enumerate(audio_json['track']['itemListElement']):
            audio_url = 'https://buoyantunrealisticmodule.m4rk4.repl.co/audio?url=' + quote_plus(track['item']['@id'])
            audio_src = ''
            if track['item'].get('additionalProperty'):
              for prop in track['item']['additionalProperty']:
                if 'mp3' in prop['name']:
                  audio_src = prop['value']
                  break
            if audio_src:
              item['content_html'] += '<tr><td style="width:50%; height:3em;">{0}.&nbsp;<a href="{1}">{2}</a></td><td><audio controls><source src="{3}" type="audio/mpeg"><a href="{3}">Play track</a></audio></td></tr>'.format(i+1, track['item']['@id'], track['item']['name'], audio_url)
            else:
              item['content_html'] += '<tr><td colspan="2" style="height:3em;">{0}.&nbsp;<a href="{1}">{2}</a></td><td>'.format(i+1, track['item']['@id'], track['item']['name'])
          item['content_html'] += '</table></center>'
          if args and 'embed' in args and item.get('summary'):
            item['content_html'] += '<p>{}</p>'.format(item['summary'])

  return item

def get_feed(args, save_debug):
  return None