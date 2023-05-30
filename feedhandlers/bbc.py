import json, re
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import bbcarticle, bbcnews, bbcsport, rss

import logging
logger = logging.getLogger(__name__)

def get_initial_data(url):
  article_html = utils.get_url_html(url)
  if not article_html:
    return None
  m = re.search('window\.__INITIAL_DATA__="(.+?)";<\/script>', article_html)
  if not m:
    logger.warning('unable to find __INITIAL_DATA__ in ' + url)
    return None
  #utils.write_file(m.group(1), './debug/debug.txt')
  data = m.group(1).replace('\\"', '"')
  data = data.replace('\\"', '\"')
  initial_data = json.loads(data)
  return initial_data

def get_video_src(vpid):
  video_src = ''
  caption = ''
  #media_js = utils.get_url_html('https://open.live.bbc.co.uk/mediaselector/6/select/version/2.0/mediaset/pc/vpid/{}/format/json/jsfunc/JS_callbacks0'.format(vpid))
  #if media_js:
  #  media_json = json.loads(media_js[19:-2])
  media_json = utils.get_url_json('https://open.live.bbc.co.uk/mediaselector/6/select/version/2.0/mediaset/pc/vpid/{}/format/json/jsfunc'.format(vpid))
  if media_json:
    if media_json.get('media'):
      for media in media_json['media']:
        if media['kind'] == 'video':
          for connection in media['connection']:
            if connection['transferFormat'] == 'hls' and connection['protocol'] == 'https':
              return connection['href'], caption
    elif media_json.get('result'):
      if media_json['result'] == 'geolocation':
        caption = 'This content is not available in your location'
  else:
    logger.warning('unable to get media info for vid ' + vpid)
    caption = 'Unable to get video info'
  return video_src, caption

def get_av_content(url, args, site_json, save_debug=False):
  initial_data = get_initial_data(url)
  if save_debug:
    utils.write_file(initial_data, './debug/debug.json')

  article_json = None
  for key, val in initial_data['data'].items():
    if key.startswith('media-experience'):
      article_json = val
  if not article_json:
    logger.warning('unable to find article content in ' + url)

  item = {}
  item['id'] = article_json['props']['id']
  item['url'] = url
  for it in article_json['data']['initialItem']['pageMetadata']['linkTags']:
    if it['rel'] == 'canonical':
      item['url'] = it['href']
  item['title'] = article_json['data']['initialItem']['structuredData']['name']

  dt = datetime.fromisoformat(article_json['data']['initialItem']['structuredData']['uploadDate'])
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = utils.format_display_date(dt)

  item['author'] = {"name": "BBC News"}

  item['tags'] = []
  for it in article_json['data']['initialItem']['mediaItem']['metadata']['items']:
    if it['label'] == 'Section' or it['label'] == 'Subsection':
      item['tags'].append(it['text'])
  if not item.get('tags'):
    del item['tags']

  images = []
  for it in article_json['data']['initialItem']['structuredData']['thumbnailUrl']:
    m = re.search(r'\/ic\/(\d+)', it)
    if m:
      images.append({"width": m.group(1), "url": it})
  if images:
    item['_image'] = utils.closest_dict(images, 'width', 1000)['url']

  item['summary'] = article_json['data']['initialItem']['structuredData']['description']

  item['content_html'] = ''
  if article_json['data']['initialItem']['mediaItem']['media']['__typename'] == 'ElementsMediaPlayer':
    video_src, caption = get_video_src(article_json['data']['initialItem']['mediaItem']['media']['items'][0]['id'])
    poster = article_json['data']['initialItem']['mediaItem']['media']['items'][0]['holdingImageUrl'].replace('$recipe', '976x549')
    if video_src:
      caption = article_json['data']['initialItem']['mediaItem']['media']['items'][0]['title']
      item['content_html'] += utils.add_video(video_src, 'application/x-mpegURL', poster, caption)
    else:
      poster = '{}/image?url={}&overlay=video'.format(config.server, quote_plus(poster))
      item['content_html'] += utils.add_image(poster, caption)

  else:
    logger.warning('unhandled media typename {} in {}'.format(article_json['data']['initialItem']['mediaItem']['media']['__typename'], url))

  item['content_html'] += bbcnews.format_content(article_json['data']['initialItem']['mediaItem']['summary'])
  return item

def get_content(url, args, site_json, save_debug=False):
  if '/av/' in url:
    return get_av_content(url, args, site_json, save_debug)
  elif '/article/' in url:
    return bbcarticle.get_content(url, args, site_json, save_debug)
  elif '/news/' in url:
    return bbcnews.get_content(url, args, site_json, save_debug)
  elif '/sport/' in url:
    return bbcsport.get_content(url, args, site_json, save_debug)
  else:
    logger.warning('unknown BBC handler for ' + url)
    return None

def get_feed(url, args, site_json, save_debug=False):
  # RSS feeds: https://www.bbc.co.uk/news/10628494
  if 'rss.xml' in args['url']:
    return rss.get_feed(url, args, site_json, save_debug, get_content)
  else:
    return bbcarticle.get_feed(url, args, site_json, save_debug)