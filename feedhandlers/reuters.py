import json, re
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

from feedhandlers import fusion
import utils

import logging
logger = logging.getLogger(__name__)

def resize_image(image_item, width_target):
  images = []
  for key, val in image_item['renditions']['original'].items():
    image = {}
    image['width'] = int(key[:-1])
    image['url'] = val
    images.append(image)
  image = utils.closest_dict(images, 'width', width_target)
  return image['url']

def get_item(content, url, args, save_debug):
  item = {}
  item['id'] = content['id']
  item['url'] = 'https://www.reuters.com' + content['canonical_url']
  item['title'] = content['title']

  dt = datetime.fromisoformat(content['published_time'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt = datetime.fromisoformat(content['updated_time'].replace('Z', '+00:00'))
  item['date_modified'] = dt.isoformat()

  # Check age
  if 'age' in args:
    if not utils.check_age(item, args):
      return None

  authors = []
  for byline in content['authors']:
    authors.append(byline['name'])
  if authors:
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

  item['tags'] = content['taxonomy']['keywords'].copy()

  lead_image = None
  if content['promo_items'].get('images'):
    lead_image = content['promo_items']['images'][0]
    item['_image'] = resize_image(content['promo_items']['images'][0], 480)

  item['summary'] = content['description']

  item['content_html'] = fusion.get_content_html(content, lead_image, resize_image, url, save_debug)
  return item

def get_content(url, args, save_debug=False, d=''):
  split_url = urlsplit(url)
  if not d:
    d = fusion.get_domain_value('{}://{}'.format(split_url.scheme, split_url.netloc))
    if not d:
      return None

  query = '{{"uri":"{0}", "website":"reuters", "published":"true", "website_url":"{0}","arc-site":"reuters"}}'.format(split_url.path)
  api_url = 'https://www.reuters.com/pf/api/v3/content/fetch/article-by-id-or-url-v1?query={}&d={}&_website=reuters'.format(quote_plus(query), d)

  if save_debug:
    logger.debug('getting content from ' + api_url)
  url_json = utils.get_url_json(api_url)
  if not (url_json and url_json.get('result')):
    return None

  content = url_json['result']
  if save_debug:
    with open('./debug/debug.json', 'w') as file:
      json.dump(content, file, indent=4)

  return get_item(content, url, args, save_debug)

def get_feed(args, save_debug=False):
  split_url = urlsplit(args['url'])
  d = fusion.get_domain_value('{}://{}'.format(split_url.scheme, split_url.netloc))
  if not d:
    return None

  section = split_url.path
  if section.endswith('/'):
    section = section[:-1]
  #query = '{{"fetch_type":"section","id":"{}","orderby":"last_updated_date:desc","size":10,"website":"reuters"}}'.format(section)
  query = '{{"uri":"/technology/","website":"reuters","id":"{0}","fetch_type":"collection","orderby":"last_updated_date:desc","size":"20","section_id":"{0}","arc-site":"reuters"}}'.format(section)
  api_url = 'https://www.reuters.com/pf/api/v3/content/fetch/articles-by-section-alias-or-id-v1?query={}&d={}&_website=reuters'.format(quote_plus(query), d)
  section_json = utils.get_url_json(api_url)
  if not section_json:
    return None
  if save_debug:
    with open('./debug/feed.json', 'w') as file:
      json.dump(section_json, file, indent=4)
  
  n = 0
  items = []
  for article in section_json['result']['articles']:
    url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, article['canonical_url'])

    # Check age (make a fake item with the timestamp)
    item = {}
    dt_pub = datetime.fromisoformat(article['published_time'].replace('Z', '+00:00'))
    item['_timestamp'] = dt_pub.timestamp()
    if args.get('age'):
      if not utils.check_age(item, args):
        if save_debug:
          logger.debug('skipping old article ' + url)
        continue

    item = get_content(url, args, save_debug, d)
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