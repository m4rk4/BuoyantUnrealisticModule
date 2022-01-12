import math, re
from datetime import datetime
from urllib.parse import quote_plus

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
  # https://omny.fm/shows/blindsided/03-paul-bissonnette/embed
  m = re.search(r'\/shows\/([^\/]+)\/([^\/]+)', url)
  if not m:
    return None

  audio_json = utils.get_url_json('https://omny.fm/api/embed/shows/{}/clip/{}'.format(m.group(1), m.group(2)))
  if not audio_json:
    return None
  if save_debug:
    utils.write_file(audio_json, './debug/audio.json')

  item = {}
  item['id'] = audio_json['Id']
  item['url'] = audio_json['OmnyShareUrl']
  item['title'] = audio_json['Title']

  dt = datetime.fromisoformat(re.sub('\.\d+Z$', '+00:00', audio_json['PublishedUtc']))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  item['author'] = {}
  item['author']['name'] = audio_json['Program']['Name']

  item['_image'] = audio_json['Images']['Small']
  item['_audio'] = utils.get_redirect_url(audio_json['AudioUrl'])
  item['summary'] = audio_json['DescriptionHtml']

  duration = []
  t = math.floor(float(audio_json['DurationMilliseconds']) / 3600000)
  if t >= 1:
    duration.append('{} hr'.format(t))
  t = math.ceil((float(audio_json['DurationMilliseconds']) - 3600000 * t) / 60000)
  if t > 0:
    duration.append('{} min.'.format(t))

  poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))
  desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by <a href="{}">{}</a><br/>{}</small>'.format(item['url'], item['title'], audio_json['Program']['ShowPageUrl'], item['author']['name'], ', '.join(duration))
  item['content_html'] = '<div><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><div>{}</div><div style="clear:left;"></div>'.format(item['_audio'], poster, desc)
  if not 'embed' in args:
    item['content_html'] += '<blockquote><small>{}</small></blockquote>'.format(item['summary'])
  item['content_html'] += '</div>'
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)