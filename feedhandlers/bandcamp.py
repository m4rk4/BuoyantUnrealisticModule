import json
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, unquote_plus

import config, utils

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, site_json, save_debug=False):
  if '/EmbeddedPlayer/' in url:
    embed_url = url
  else:
    bc_html = utils.get_url_html(url)
    if not bc_html:
      return None
    soup = BeautifulSoup(bc_html, 'html.parser')
    el = soup.find('meta', attrs={"property":"og:video"})
    if not el:
      logger.warning('unable to find the EmbeddedPlayer url in ' + url)
      return None
    embed_url = el['content']

  bc_html = utils.get_url_html(embed_url)
  if not bc_html:
    return None

  soup = BeautifulSoup(bc_html, 'html.parser')
  el = soup.find('script', attrs={"data-player-data": True})
  if not el:
    logger.warning('unable to find data-player-data in ' + embed_url)
    return None

  bc_json = json.loads(unquote_plus(el['data-player-data']))
  if save_debug:
    utils.write_file(bc_json, './debug/bandcamp.json')

  item = {}
  if '/track=' in embed_url:
    if bc_json.get('album_id'):
      album_item = get_content('https://bandcamp.com/EmbeddedPlayer/v=2/album={}/size=large/tracklist=false/artwork=small/'.format(bc_json['album_id']), args, site_json, save_debug)
    else:
      album_item = None

    track = bc_json['tracks'][0]
    item['id'] = track['id']
    item['url'] = track['title_link']
    item['title'] = track['title']
    item['author'] = {}
    item['author']['name'] = track['artist']

    if track.get('file'):
      for key, val in track['file'].items():
        if 'mp3' in key:
          item['_audio'] = val
          break

    if track.get('art'):
      item['_image'] = track['art']
    else:
      item['_image'] = bc_json['album_art']

    if item.get('_audio'):
      if 'embed' in args:
        audio_src = '{}/audio?url={}'.format(config.server, quote_plus(item['url']))
      else:
        audio_src = item['_audio']
      poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))
    else:
      audio_src = item['url']
      poster = '{}/image?height=128&url={}'.format(config.server, quote_plus(item['_image']))

    desc = '<b><a href="{}">{}</a></b><br/>'.format(item['url'], item['title'])
    if track['artist'] == bc_json['artist']:
      desc += 'by <a href="{}">{}</a><br/>'.format(bc_json['band_url'], track['artist'])
    else:
      desc += 'by {}<br/>'.format(track['artist'])
    if album_item:
      desc += 'from <a href="{}">{}</a>'.format(album_item['url'], album_item['title'])
    else:
      desc += 'from {}'.format(bc_json['album_title'])

    item['content_html'] = '<div><a href="{}"><img style="float:left; margin-right:8px; height:128px;" src="{}"/></a><div style="overflow:auto; display:block;">{}</div><div style="clear:left;"></div></div>'.format(audio_src, poster, desc)

  elif '/album=' in embed_url:
    item['id'] = bc_json['album_id']
    item['url'] = bc_json['linkback']
    item['title'] = bc_json['album_title']

    item['author'] = {}
    for track in bc_json['tracks']:
      if track['artist'] != bc_json['artist']:
        item['author']['name'] = 'Various Artists'
        break
    if not item['author'].get('name'):
      item['author']['name'] = bc_json['artist']

    item['_image'] = bc_json['album_art']
    poster = '{}/image?height=128&url={}'.format(config.server, quote_plus(item['_image']))
    audio_src = bc_json['linkback']

    desc = '<b><a href="{}">{}</a></b><br/>'.format(item['url'], item['title'])
    desc += 'by <a href="{}">{}</a>'.format(bc_json['band_url'], item['author']['name'])

    item['content_html'] = '<div><a href="{}"><img style="float:left; margin-right:8px; height:128px;" src="{}"/></a><div style="overflow:auto; display:block;">{}</div><div style="clear:left;"></div><b>Tracks:</b><ol>'.format(audio_src, poster, desc)

    for track in bc_json['tracks']:
      item['content_html'] += '<li><a href="{}">{}</a>'.format(track['title_link'], track['title'])
      if track['artist'] != item['author']['name']:
        item['content_html'] += ' by {}'.format(track['artist'])
      if track.get('file'):
        for key, val in track['file'].items():
          if 'mp3' in key:
            if 'embed' in args:
              audio_src = '{}/audio?url={}'.format(config.server, quote_plus(item['url']))
            else:
              audio_src = val
            item['content_html'] += ' <a href="{}">(&#9658;&nbsp;Play)</a>'.format(audio_src)
            break
      item['content_html'] += '</li>'

    item['content_html'] += '</ol></div>'

  dt = datetime.strptime(bc_json['publish_date'], '%d %b %Y %H:%M:%S %Z').replace(tzinfo=timezone.utc)
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  return item

def get_feed(url, args, site_json, save_debug):
  return None