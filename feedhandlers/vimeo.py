import json, re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug):
  split_url = urlsplit(url)

  vimeo_id = ''
  if split_url.path.startswith('/video'):
    vimeo_id = split_url.path.split('/')[2]
  else:
    vimeo_id = split_url.path.split('/')[1]

  if not vimeo_id.isnumeric():
    logger.warning('unable to determine Vimeo id in ' + url)
    return None

  player_url = 'https://player.vimeo.com/video/{}'.format(vimeo_id)
  vimeo_html = utils.get_url_html(player_url, 'desktop')
  if not vimeo_html:
    return None

  m = re.search(r'var config = (\{.*?\});', vimeo_html)
  if not m:
    logger.warning('unable to parse player config in ' + player_url)
    return None

  try:
    vimeo_json = json.loads(m.group(1))
  except:
    logger.warning('error loading player config json from ' + player_url)

  if save_debug:
    utils.write_file(vimeo_json, './debug/vimeo.json')

  item = {}
  item['id'] = vimeo_id
  item['url'] = vimeo_json['video']['share_url']
  item['title'] = vimeo_json['video']['title']

  #dt = datetime.strptime(vimeo_json['clip']['uploaded_on'], '%Y-%m-%d %H:%M:%S').astimezone(timezone.utc)
  #item['date_published'] = dt.isoformat()
  #item['_timestamp'] = dt.timestamp()
  #item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  item['author'] = {}
  item['author']['name'] = vimeo_json['video']['owner']['name']

  if vimeo_json['video']['thumbs'].get('base'):
    item['_image'] = vimeo_json['video']['thumbs']['base'] + '_1000'

  if not vimeo_json['video'].get('live_event'):
    video = utils.closest_dict(vimeo_json['request']['files']['progressive'], 'width', 640)
    item['_video'] = video['url']
    caption = '{} | <a href="{}">Watch on Vimeo</a>'.format(item['title'], player_url)
    if args and args.get('embed'):
      video_src = '{}/video?url={}'.format(config.server, quote_plus(item['url']))
      item['content_html'] = utils.add_video(video_src, 'video/mp4', item['_image'], caption)
    else:
      item['content_html'] = utils.add_video(video['url'], video['mime'], item['_image'], caption)
  else:
    poster = '{}/image?url={}&overlay=video'.format(config.server, quote_plus(item['_image']))
    item['content_html'] = utils.add_image(poster, 'Live event: {}'.format(item['title']), link=item['url'])
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)