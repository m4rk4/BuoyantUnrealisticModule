import math, re
from datetime import datetime
from urllib.parse import quote_plus

import config, utils

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
  # Only handles single episodes
  # https://playlist.megaphone.fm/?e=ESP3970143369
  m = re.search(r'e=(ESP\d+)', url)
  if not m:
    logger.warning('unable to parse episode id from ' + url)
    return None

  podcast_json = utils.get_url_json('https://player.megaphone.fm/playlist/episode/{}'.format(m.group(1)))
  if not podcast_json:
    return None
  if save_debug:
    utils.write_file(podcast_json, './debug/podcast.json')

  episode = podcast_json['episodes'][0]

  item = {}
  item['id'] = episode['uid']
  item['url'] = 'https://playlist.megaphone.fm/?e={}'.format(episode['uid'])
  item['title'] = episode['title']

  dt = datetime.fromisoformat(episode['pubDate'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  item['author'] = {}
  item['author']['name'] = podcast_json['podcastTitle']

  item['_image'] = episode['imageUrl']
  item['_audio'] = episode['episodeUrlHRef']

  item['summary'] = episode['summary']

  poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))
  duration = []
  t = math.floor(float(episode['duration']) / 3600)
  if t >= 1:
    duration.append('{} hr'.format(t))
  t = math.ceil((float(episode['duration']) - 3600 * t) / 60)
  if t > 0:
    duration.append('{} min.'.format(t))
  desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by {}<br/>{}</small>'.format(item['url'], item['title'], item['author']['name'], ', '.join(duration))
  item['content_html'] = '<center><table style="width:360px; border:1px solid black; border-radius:10px; border-spacing:0;"><tr><td style="width:1%; padding:0; margin:0;"><a href="{}"><img style="display:block; border-top-left-radius:10px; border-bottom-left-radius:10px;" src="{}" /></a></td><td style="padding-left:0.5em; vertical-align:top;">{}</td></tr></table></center>'.format(item['_audio'], poster, desc)
  if not 'embed' in args:
    item['content_html'] += '<p>{}</p>'.format(item['summary'])

  return

def get_feed(args, save_debug=False):
  return None
