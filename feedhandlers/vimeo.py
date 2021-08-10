import json, re
from datetime import datetime, timezone

from feedhandlers import rss
import utils

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug):
  vimeo_id = ''
  m = re.search(r'vimeo\.com\/(\d+)', url)
  if m:
    vimeo_id = m.group(1)

  if not vimeo_id:
    logger.warning('unable to determine Vimeo id in ' + url)
    return None

  vimeo_config = None
  vimeo_html = utils.get_url_html('https://vimeo.com/' + vimeo_id, 'desktop', use_proxy=True)
  if vimeo_html:
    m = re.search('window.vimeo.clip_page_config = ([^;]+);', vimeo_html)
    if m:
      vimeo_json = json.loads(m.group(1))
      vimeo_config = utils.get_url_json(vimeo_json['player']['config_url'])

  if not vimeo_config:
    return None
  if save_debug:
    with open('./debug/vimeo.json', 'w') as file:
      json.dump(vimeo_config, file, indent=4)

  item = {}
  item['id'] = vimeo_id
  item['url'] = url
  item['title'] = vimeo_json['clip']['title']

  dt_pub = datetime.strptime(vimeo_json['clip']['uploaded_on'], '%Y-%m-%d %H:%M:%S').astimezone(timezone.utc)
  item['date_published'] = dt_pub.isoformat()
  item['_timestamp'] = dt_pub.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  item['author'] = {}
  item['author']['name'] = vimeo_json['owner']['display_name']

  item['_image'] = vimeo_config['video']['thumbs']['640']

  video = utils.closest_dict(vimeo_config['request']['files']['progressive'], 'width', 640)
  item['_video'] = video['url']

  item['content_html'] = utils.add_video(video['url'], video['mime'], vimeo_config['video']['thumbs']['640'], '', video['width'], video['height'])

  return item

def get_feed(args, save_debug=False):
  n = 0
  items = []
  feed = rss.get_feed(args, save_debug)
  print(feed)
  for feed_item in feed['items']:
    if save_debug:
      logger.debug('getting content for ' + feed_item['url'])
    item = get_content(feed_item['url'], args, save_debug)
    if item:
      if utils.filter_item(item, args) == True:
        items.append(item)
        n += 1
        if 'max' in args:
          if n == int(args['max']):
            break
  feed['items'] = items.copy()
  return feed