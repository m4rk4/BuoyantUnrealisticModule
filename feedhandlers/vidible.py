import json, re
from datetime import datetime

import utils

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
  # This probably only works for embed urls for now
  # https://delivery.vidible.tv/htmlembed/pid=5706c5c8e4b03b51471aefba/564f3144ff690c0a7c285e51.html?vid=61259d340815f73ecceceea1&amp;m.playback=autoplay&amp;m.disable_moat=1
  m = re.search(r'vid=([0-9a-f]+)', url)
  if not m:
    logger.warning('unable to parse Vidible vid in ' + url)
    return None
  vid = m.group(1)

  vid_html = utils.get_url_html(url)
  if not vid_html:
    return None

  m = re.search(r'var DS_URL = \'([^\']+)\'', vid_html)
  if not m:
    logger.warning('unable to parse Vidible DS_URL in ' + url)
    return None

  ds_url = 'https:' + m.group(1)
  ds_js = utils.get_url_html(ds_url)
  if save_debug:
    utils.write_file(ds_js, './debug/debug.txt')

  m = re.search(r'var a=(\{.*\});a\.', ds_js)
  if not m:
    logger.warning('unable to parse Vidible json in ' + ds_url)
    return None

  ds_json = json.loads(m.group(1))
  if save_debug:
    utils.write_file(ds_json, './debug/vidible.json')

  for video in ds_json['placementJSON']['bid']['videos']:
    if video['videoId'] == vid:
      item = {}
      item['id'] = vid
      item['url'] = url
      item['title'] = video['name']
      item['author'] = {}
      item['author']['name'] = video['studioName']
      if video['metadata'].get('keywords'):
        item['tags'] = video['metadata']['keywords'].copy()
      if video.get('description'):
        item['summary'] = video['description']
      item['_image'] = video['fullsizeThumbnail']
      video_src = ''
      for video_type in ['mp4', 'm3u8']:
        for video_url in video['videoUrls']:
          if video_type in video_url:
            video_src = video_url
            break
        if video_src:
          break
      if 'mp4' in video_src:
        video_type = 'video/mp4'
      else:
        video_type = 'application/x-mpegURL'
      item['content_html'] = utils.add_video(video_src, video_type, item['_image'], item['title'])
      m = re.search(r'\/prod\/[0-9a-f]+\/(\d{4}-\d\d-\d\d)\/', video_src)
      if m:
        dt = datetime.fromisoformat(m.group(1))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
      break
  return item

def get_feed(args, save_debug=False):
  return None