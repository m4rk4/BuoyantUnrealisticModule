import re
from datetime import datetime
from urllib.parse import urlsplit

import utils

import logging
logger = logging.getLogger(__name__)

def get_token():
  token_json = utils.get_url_json('https://www.hackster.io/users/api_token')
  if not token_json:
    logger.warning('unable to get Hackster token')
    return ''
  return token_json['client_token']

def resize_image(img_src, width=1000):
  split_url = urlsplit(img_src)
  return '{}://{}{}?auto=compress%2Cformat&w={}'.format(split_url.scheme, split_url.netloc, split_url.path, width)

def format_content(el):
  content_html = ''
  if el['tag'] == 'a':
    start_tag = '<a href={}>'.format(el['attribs']['href'])
    end_tag = '</a>'
  else:
    start_tag = '<{}>'.format(el['tag'])
    end_tag = '</{}>'.format(el['tag'])
  if el.get('content'):
    content_html += start_tag + el['content'] + end_tag
  elif el.get('children'):
    for child in el['children']:
      content_html += format_content(child)
  return content_html

def get_content_by_id(article_id, args, save_debug=False):
  post_data = {"t": "news_article","variables": {"id": int(article_id)}}

  sites_json = utils.read_json_file('./sites.json')
  token = sites_json['hackster']['token']
  article_json = utils.post_url('https://api.hackster.io/graphql/query?bearer_token=' + token, json_data=post_data)
  if not article_json:
    token = get_token()
    if token:
      article_json = utils.post_url('https://api.hackster.io/graphql/query?bearer_token=' + token, json_data=post_data)
    if not article_json:
      return None
    logger.debug('updating Hackster token')
    sites_json['hackster']['token'] = token
    utils.write_file(sites_json, './sites.json')

  if save_debug:
    utils.write_file(article_json, './debug/debug.json')

  item = {}
  item['id'] = article_id
  item['url'] = article_json['article']['url']
  item['title'] = article_json['article']['title']

  dt = datetime.fromisoformat(article_json['article']['published_at'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = utils.format_display_date(dt)
  dt = datetime.fromisoformat(article_json['article']['updated_at'].replace('Z', '+00:00'))
  item['date_modified'] = dt.isoformat()

  item['author'] = {}
  item['author']['name'] = article_json['article']['user']['name']

  item['tags'] = []
  if article_json['article'].get('tags'):
    for tag in article_json['article']['tags']:
      tag_name = tag['name'].lower()
      if tag_name not in item['tags']:
        item['tags'].append(tag_name)
  if article_json['article'].get('topics'):
    for tag in article_json['article']['topics']:
      tag_name = tag['name'].lower()
      if tag_name not in item['tags']:
        item['tags'].append(tag_name)
  if article_json['article'].get('platforms'):
    for tag in article_json['article']['platforms']:
      tag_name = tag['name'].lower()
      if tag_name not in item['tags']:
        item['tags'].append(tag_name)
  if article_json['article'].get('products'):
    for tag in article_json['article']['products']:
      tag_name = tag['name'].lower()
      if tag_name not in item['tags']:
        item['tags'].append(tag_name)

  if article_json['article']['image'].get('url'):
    item['_image'] = article_json['article']['image']['url']

  item['summary'] = article_json['article']['summary']

  item['content_html'] = ''
  for content in article_json['article']['content']:
    if content['type'] == 'CE':
      for el in content['json']:
        item['content_html'] += format_content(el)
    elif content['type'] == 'Carousel':
      for image in content['images']:
        item['content_html'] += utils.add_image(resize_image(image['url']), image['figcaption'])
    elif content['type'] == 'Video':
      for video in content['video']:
        if video['service'] == 'youtube':
          item['content_html'] += utils.add_embed(video['embed'])
        elif video['service'] == 'mp4':
          item['content_html'] += utils.add_video(video['embed'], 'video/mp4', '', video['figcaption'])
        else:
          logger.warning('unhandled video in service {} in {}'.format(video['service'], item['url']))
    else:
      logger.warning('unhandled content type {} in {}'.format(content['type'], item['url']))
  return item

def get_content(url, args, save_debug=False):
  article_html = utils.get_url_html(url)
  m = re.search(r'\'entityId\':\s?\"(\d+)\"', article_html)
  if not m:
    return None
  return get_content_by_id(m.group(1), args, save_debug)

def get_feed(args, save_debug=False):
  feed = None
  if '/news/' in args['url']:
    post_data = {"t": "news_articles_simple_pagination", "variables": {"offset": 0, "per_page": 10, "by_sponsored":False, "by_status_type": "PUBLISHED", "sort": "PUBLISHED_AT"}}
    m = re.search(r'topic=([^\&]+)', urlsplit(args['url']).query)
    if m:
      if m.group(1) == 'iot':
        post_data['variables']['by_topic_id'] = 77307
      elif m.group(1) == 'ml':
        post_data['variables']['by_topic_id'] = 5261
      elif m.group(1) == 'sensors':
        post_data['variables']['by_topic_id'] = 5960
      elif m.group(1) == 'covid19':
        post_data['variables']['by_topic_id'] = 333550
      elif m.group(1) == 'hw101':
        post_data['variables']['by_topic_id'] = 22477
    sites_json = utils.read_json_file('./sites.json')
    token = sites_json['hackster']['token']
    articles_json = utils.post_url('https://api.hackster.io/graphql/query?bearer_token=' + token, json_data=post_data)
    if not articles_json or (articles_json and not articles_json['articles'].get('records')):
      token = get_token()
      if token:
        articles_json = utils.post_url('https://api.hackster.io/graphql/query?bearer_token=' + token, json_data=post_data)
      if not articles_json:
        return None
      logger.debug('updating Hackster token')
      sites_json['hackster']['token'] = token
      utils.write_file(sites_json, './sites.json')
    if save_debug:
      utils.write_file(articles_json, './debug/feed.json')

  n = 0
  items = []
  for article in articles_json['articles']['records']:
    if save_debug:
      logger.debug('getting content for ' + article['url'])
    item = get_content_by_id(article['id'], args, save_debug)
    if item:
      if utils.filter_item(item, args) == True:
        items.append(item)
        n += 1
        if 'max' in args:
          if n == int(args['max']):
            break
  feed = utils.init_jsonfeed(args)
  feed['items'] = items.copy()
  return feed
