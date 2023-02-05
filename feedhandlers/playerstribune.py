import json, re
from datetime import datetime

import utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)

def resize_image(host, path, width=1000):
  return host + 'c_fill,w_{},f_auto,q_auto,g_auto/'.format(width) + path

def add_image(image):
  img_src = resize_image(image['host'], image['path'])
  captions = []
  if image.get('caption'):
    captions.append(image['caption'].encode('iso-8859-1').decode('utf-8'))
  if image.get('credit'):
    captions.append(image['credit'].encode('iso-8859-1').decode('utf-8'))
  return utils.add_image(img_src, ' | '.join(captions))

def get_content(url, args, site_json, save_debug):
  article_html = utils.get_url_html(url)
  if not article_html:
    return None

  m = re.search(r'window\.__PRELOADED_STATE__ = ({.+})\s+<\/script>', article_html, flags=re.S)
  if not m:
    logger.warning('unable to parse __PRELOADED_STATE__ in '+ url)
    return None

  article_json = json.loads(m.group(1))
  if save_debug:
    utils.write_file(article_json, './debug/debug.json')

  item = {}
  item['id'] = article_json['template']['articleId']
  item['url'] = url
  item['title'] = article_json['template']['title']

  dt = datetime.fromisoformat(article_json['template']['createdAt'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt = datetime.fromisoformat(article_json['template']['updatedAt'].replace('Z', '+00:00'))
  item['date_modified'] = dt.isoformat()

  authors = []
  for author in article_json['template']['authors']:
    authors.append(author['name'])
  if authors:
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

  item['tags'] = article_json['template']['tags'].copy()

  item['summary'] = article_json['template']['metadataDescription']

  item['content_html'] =  ''
  if article_json['template']['cover'].get('image'):
    item['_image'] = article_json['template']['cover']['image']['host'] + article_json['template']['cover']['image']['path']
    item['content_html'] += add_image(article_json['template']['cover']['image'])

  for content in article_json['template']['body']:
    if content['type'] == 'inline-text':
      item['content_html'] += content['html'].encode('iso-8859-1').decode('utf-8')

    elif content['type'] == 'image':
      item['content_html'] += add_image(content['image'])

    elif re.search(r'iframeEmbed|ceros|gfycat|youtube', content['type']):
      m = re.search('src="([^"]+)"', content['html'])
      src = m.group(1)
      if src.startswith('//'):
        src = 'https:' + src
      item['content_html'] += utils.add_embed(src)

    elif content['type'] == 'mmPlayer':
      video_json = utils.get_url_json('https://videos-content.voltaxservices.io/{0}/{0}.json'.format(content['mediaId']))
      if video_json:
        if save_debug:
          utils.write_file(video_json, './debug/video.json')
        videos = []
        for src in video_json['data'][0]['sources']:
          if 'mp4' in src['type'] and src.get('height'):
            videos.append(src)
        video = utils.closest_dict(videos, 'height', 480)
        caption = video_json['data'][0].get('description')
        if not caption:
          caption = video_json['data'][0].get('title')
        item['content_html'] += utils.add_video(video['file'], video['type'], video_json['data'][0]['image'], caption)
      else:
        logger.warning('unhandled mmPlayer video in ' + url)

    elif content['type'] == 'quote':
      item['content_html'] += utils.add_pullquote(content['text'].encode('iso-8859-1').decode('utf-8'), content['cite'])

    elif content['type'] == 'divider':
      item['content_html'] += '<hr/>'

    else:
      logger.warning('unhandled content type {} in {}'.format(content['type'], url))

  return item

def get_feed(url, args, site_json, save_debug=False):
  # Topic feeds: https://www.theplayerstribune.com/api/properties/theplayertribune/posts?topic=football&limit=10
  return rss.get_feed(url, args, site_json, save_debug, get_content)