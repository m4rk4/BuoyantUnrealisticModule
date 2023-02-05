import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, site_json, save_debug):
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

  soup = BeautifulSoup(vimeo_html, 'lxml')
  el = soup.find('script', string=re.compile(r'window\.playerConfig'))
  if not el:
    logger.warning('unable to parse playerConfig in ' + player_url)
    return None

  i = el.string.find('{')
  m = re.search(r'^({.*?});?\s+var', el.string[i:])
  if m:
    vimeo_json = json.loads(m.group(1))
  else:
    utils.write_file(el.string, './debug/vimeo.txt')
    logger.warning('error converting playerConfig to json in' + player_url)
    return None

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
    if vimeo_json['request']['files'].get('progressive'):
      video = utils.closest_dict(vimeo_json['request']['files']['progressive'], 'width', 640)
      video_type = 'video/mp4'
    elif vimeo_json['request']['files'].get('hls'):
      for key, val in vimeo_json['request']['files']['hls']['cdns'].items():
        video = val
        video_type = 'application/x-mpegURL'
        break
    item['_video'] = video['url']
    caption = '{} | <a href="{}">Watch on Vimeo</a>'.format(item['title'], player_url)
    if args and args.get('embed'):
      video_src = '{}/video?url={}'.format(config.server, quote_plus(item['url']))
      item['content_html'] = utils.add_video(video_src, video_type, item['_image'], caption)
    else:
      item['content_html'] = utils.add_video(video['url'], video_type, item['_image'], caption)
  else:
    poster = '{}/image?url={}&overlay=video'.format(config.server, quote_plus(item['_image']))
    item['content_html'] = utils.add_image(poster, 'Live event: {}'.format(item['title']), link=item['url'])
  return item

def get_feed(url, args, site_json, save_debug=False):
  return rss.get_feed(url, args, site_json, save_debug, get_content)