import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, unquote_plus

import config
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
        poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(audio_json['image']))

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
          audio_src = '{}/audio?url={}'.format(config.server, quote_plus(audio_json['@id']))
          desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>'.format(audio_json['@id'], audio_json['name'])
          if audio_json.get('inAlbum') and audio_json['inAlbum'].get('@id'):
            desc += 'from <a href="{}">{}</a><br/>'.format(audio_json['inAlbum']['@id'], audio_json['inAlbum']['name'])
          if audio_json.get('byArtist'):
            if audio_json['byArtist'].get('@id'):
              desc += 'by <a href="{}">{}</a>'.format(audio_json['byArtist']['@id'], audio_json['byArtist']['name'])
            elif audio_json.get('publisher') and audio_json['publisher'].get('@id'):
              desc += 'by <a href="{}">{}</a>'.format(audio_json['publisher']['@id'], audio_json['byArtist']['name'])
            else:
              desc += 'by {}'.format(audio_json['byArtist']['name'])
          desc += '</small>'
          item['content_html'] = '<center><table style="width:360px; border:1px solid black; border-radius:10px; border-spacing:0;"><tr><td style="width:1%; padding:0; margin:0;"><a href="{}"><img style="display:block; border-top-left-radius:10px; border-bottom-left-radius:10px;" src="{}" /></a></td><td style="padding-left:0.5em; vertical-align:top;">{}</td></tr></table></center>'.format(audio_src, poster, desc)

        elif audio_json['@type'] == 'MusicAlbum':
          poster = '{}/image?url={}&height=128'.format(config.server, audio_json['image'])
          desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>'.format(audio_json['@id'], audio_json['name'])
          if audio_json.get('byArtist'):
            if audio_json['byArtist'].get('@id'):
              desc += 'by <a href="{}">{}</a><br/>'.format(audio_json['byArtist']['@id'], audio_json['byArtist']['name'])
            elif audio_json.get('publisher') and audio_json['publisher'].get('@id'):
              desc += 'by <a href="{}">{}</a><br/>'.format(audio_json['publisher']['@id'], audio_json['byArtist']['name'])
            else:
              desc += 'by {}<br/>'.format(audio_json['byArtist']['name'])
          dt = datetime.strptime(audio_json['datePublished'], '%d %b %Y %H:%M:%S %Z')
          desc += 'released {}</small>'.format(dt.strftime('%b %d, %Y'))
          item['content_html'] = '<center><table style="width:360px; border:1px solid black; border-radius:10px; border-spacing:0;"><tr><td style="width:1%; padding:0; margin:0; border-bottom: 1px solid black;"><a href="{}"><img style="display:block; border-top-left-radius:10px;" src="{}" /></a></td><td style="padding-left:0.5em; vertical-align:top; border-bottom: 1px solid black;">{}</td></tr><tr><td colspan="2">Tracks:<ol style="margin-top:0;">'.format(audio_json['@id'], poster, desc)
          for track in audio_json['track']['itemListElement']:
            audio_url = '{}/audio?url={}'.format(config.server, quote_plus(track['item']['@id']))
            audio_src = ''
            if track['item'].get('additionalProperty'):
              for prop in track['item']['additionalProperty']:
                if 'mp3' in prop['name']:
                  audio_src = prop['value']
                  break
            item['content_html'] += '<li>'
            if audio_src:
              item['content_html'] += '<a style="text-decoration:none;" href="{}">&#9658;</a>&nbsp;'.format(audio_url)
            item['content_html'] += '<a href="{}">{}</a>'.format(track['item']['@id'], track['item']['name'])
            if track['item'].get('byArtist') and track['item']['byArtist']['name'] != audio_json['byArtist']['name']:
              item['content_html'] += ' by {}'.format(track['item']['byArtist']['name'])
            item['content_html'] += '</li>'
          item['content_html'] += '</ol></td></tr></table></center>'
          if args and 'embed' in args and item.get('summary'):
            item['content_html'] += '<p>{}</p>'.format(item['summary'])

  return item

def get_feed(args, save_debug):
  return None