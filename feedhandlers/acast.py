import math, re
from datetime import datetime
from urllib.parse import quote_plus

import config, utils

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
  m = re.search(r'embed\.acast\.com\/([^\/]+)\/([^\/]+)', url)
  if not m:
    m = re.search(r'play\.acast\.com\/s\/([^\/]+)\/([^\/]+)', url)
    if not m:
      return None

  audio_json = utils.get_url_json('https://feeder.acast.com/api/v1/shows/{}/episodes/{}?showInfo=true'.format(m.group(1), m.group(2)))
  if save_debug:
    utils.write_file(audio_json, './debug/audio.json')

  item = {}
  item['id'] = audio_json['id']
  item['url'] = audio_json['link']
  item['title'] = audio_json['title']

  dt = datetime.fromisoformat(audio_json['publishDate'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  item['author'] = {}
  item['author']['name'] = audio_json['show']['title']

  #if audio_json.get('keywords'):

  if audio_json.get('image'):
    item['_image'] = audio_json['image']
  elif audio_json['images'].get('original'):
    item['_image'] = audio_json['images']['original']
  elif audio_json['show'].get('image'):
    item['_image'] = audio_json['show']['image']
  elif audio_json['show']['images'].get('original'):
    item['_image'] = audio_json['show']['images']['original']

  item['_audio'] = audio_json['url']
  item['summary'] = audio_json['subtitle']

  duration = []
  t = math.floor(float(audio_json['duration']) / 3600)
  if t >= 1:
    duration.append('{} hr'.format(t))
  t = math.ceil((float(audio_json['duration']) - 3600 * t) / 60)
  if t > 0:
    duration.append('{} min.'.format(t))

  poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))
  desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by <a href="{}">{}</a><br/>{}</small>'.format(item['url'], item['title'], audio_json['show']['link'], item['author']['name'], ', '.join(duration))
  item['content_html'] = '<div><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><div>{}</div><div style="clear:left;"><blockquote><small>{}</small></blockquote></div>'.format(item['_audio'], poster, desc, item['summary'])
  return item
