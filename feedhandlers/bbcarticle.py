import json, re
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import bbc

import logging
logger = logging.getLogger(__name__)

def add_image(image):
  if image.get('SynopsisLong'):
    caption = image['SynopsisLong']
  elif image.get('SynopsisMedium'):
    caption = image['SynopsisMedium']
  elif image.get('SynopsisShort'):
    caption = image['SynopsisShort']
  else:
    caption = ''
  img_src = image['TemplateUrl'].replace('$recipe', '976x549')
  return utils.add_image(img_src, caption)

def get_article(article_json, url, args, save_debug):
  item = {}
  item['id'] = article_json['_id']
  item['url'] = url
  item['title'] = article_json['Content']['HeadlineLong']

  dt = datetime.fromisoformat(re.sub(r'\.(\d{3})\d+Z$', '.\\1Z', article_json['Metadata']['CreationDateTime']).replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = utils.format_display_date(dt)
  dt = datetime.fromisoformat(re.sub(r'\.(\d{3})\d+Z$', '.\\1Z', article_json['Metadata']['ModifiedDateTime']).replace('Z', '+00:00'))
  item['date_modified'] = dt.isoformat()

  item['author'] = {}
  if article_json['Content'].get('Author'):
    authors = []
    for author in article_json['Content']['Author']:
      authors.append(author['Content']['Name'])
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
  else:
    item['author']['name'] = 'BBC.com'

  if article_json['Content'].get('Tag'):
    item['tags'] = []
    for tag in article_json['Content']['Tag']:
      item['tags'].append(tag['Content']['Name'])

  item['summary'] = article_json['Content']['SummaryLong']

  content_html = ''
  if article_json['Content'].get('Image'):
    item['_image'] = article_json['Content']['Image'][0]['Content']['TemplateUrl'].replace('$recipe', '976x549')
    for card_image in article_json['Content']['Image']:
      content_html += add_image(card_image['Content'])

  if article_json['Content'].get('BodyIntro'):
    content_html += '<p><b>{}</b></p>'.format(article_json['Content']['BodyIntro'])

  for card in article_json['Content']['Cards']:
    if card['CardType'] == 'Body':
      content_html += card['BodyHtml']['Html']

    elif card['CardType'] == 'Image':
      for card_image in card['Image']:
        content_html += add_image(card_image['Content'])

    elif card['CardType'] == 'Video':
      for video in card['VideoUrn']:
        if video['Content'].get('Thumbnail'):
          poster = video['Content']['Thumbnail'][0]['Content']['TemplateUrl'].replace('$recipe', '976x549')
        else:
          logger.debug('no video thumbnail in ' + url)
          poster = '{}/image?width=976&height=549&overlay=video'.format(config.server)
        video_src, caption = bbc.get_video_src(video['Content']['Vpid'])
        if video_src:
          caption = video['Content']['Title']
          content_html += utils.add_video(video_src, 'application/x-mpegURL', poster, caption)
        else:
          poster = '{}/image?url={}&overlay=video'.format(config.server, quote_plus(poster))
          content_html += utils.add_image(poster, caption)

    elif card['CardType'] == 'PullQuote':
      content_html += utils.add_pullquote(card['PullQuote'])

    elif card['CardType'] == 'CalloutBox':
      content_html += '<div style="width:90%; margin-left:auto; margin-right:auto; padding:1px 1em 1px 1em; background-color:LightGray;"><h4>{}</h4>{}</div>'.format(card['CalloutTitle'], card['CalloutBodyHtml'])

    else:
      logger.warning('unhandled card type {} in {}'.format(card['CardType'], url))

  item['content_html'] = content_html.replace('<p>&nbsp;</p>', '')
  return item

def get_content(url, args, save_debug=False):
  split_url = urlsplit(url)
  json_url = '{}://{}/{}/data/site{}'.format(split_url.scheme, split_url.netloc, split_url.path.split('/')[1], split_url.path)
  article_json = utils.get_url_json(json_url)
  if not article_json:
    return None
  if save_debug:
    utils.write_file(article_json, './debug/debug.json')
  return get_article(article_json, url, args, save_debug)

def get_feed(args, save_debug=False):
  split_url = urlsplit(args['url'])
  paths = split_url.path[1:].split('/')
  feed_url = ''
  if len(paths) == 1:
    #feed_url = '{0}://{1}/{2}/data/site/{2}/module/index?page=1&itemsPerPage=10'.format(split_url.scheme, split_url.netloc, paths[0])
    feed_url = '{0}://{1}/{2}/data/site/{2}/article/homepage?page=1&itemsPerPage=10'.format(split_url.scheme, split_url.netloc, paths[0])

  elif len(paths) == 2:
    feed_url = '{0}://{1}/{2}/data/site/{2}/article/premium-collection/{3}?page=1&itemsPerPage=10'.format(split_url.scheme, split_url.netloc, paths[0], paths[1])

  elif len(paths) == 3:
    if paths[1] == 'columns':
      feed_url = '{0}://{1}/{2}/data/site/{2}/article/collection/{3}?page=1&itemsPerPage=10'.format(split_url.scheme, split_url.netloc, paths[0], paths[2])

    elif paths[1] == 'tags':
      feed_url = '{0}://{1}/{2}/data/site/{2}/article/tag/{3}?page=1&itemsPerPage=10'.format(split_url.scheme, split_url.netloc, paths[0], paths[2])

    elif paths[1] == 'destinations':
      feed_url = '{0}://{1}/{2}/data/site/{2}/article/destination-guide/{3}?page=1&itemsPerPage=10'.format(split_url.scheme, split_url.netloc, paths[0], paths[2])

  if not feed_url:
    logger.warning('unhandled feed url ' + args['url'])
    return None

  feed_json = utils.get_url_json(feed_url)
  if not feed_json:
    return None
  if save_debug:
    utils.write_file(feed_json, './debug/feed.json')

  n = 0
  items = []
  for it in feed_json['results']:
    url = '{}://{}/{}'.format(split_url.scheme, split_url.netloc, it['Metadata']['Id'])
    if save_debug:
      logger.debug('getting content for ' + url)
    item = get_article(it, url, args, save_debug)
    if item:
      if utils.filter_item(item, args) == True:
        items.append(item)
        n += 1
        if 'max' in args:
          if n == int(args['max']):
            break
  feed = utils.init_jsonfeed(args)
  feed['items'] = sorted(items, key=lambda i: i['_timestamp'], reverse=True)
  return feed