import json, re
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

from feedhandlers import fusion, nextjs, rss
import utils

import logging
logger = logging.getLogger(__name__)

def resize_image(image_item, width_target):
  return 'https://www.washingtonpost.com/wp-apps/imrs.php?src={}&w={}'.format(image_item['url'], width_target)

def get_item(content, url, args, save_debug):
  item = {}
  item['id'] = content['_id']
  item['url'] = url
  item['title'] = content['headlines']['basic']

  dt = datetime.fromisoformat(content['first_publish_date'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt = datetime.fromisoformat(content['last_updated_date'].replace('Z', '+00:00'))
  item['date_modified'] = dt.isoformat()

  authors = []
  for byline in content['credits']['by']:
    authors.append(byline['name'])
  if authors:
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

  item['tags'] = []
  if content['taxonomy'].get('seo_keywords'):
    item['tags'] = content['taxonomy']['seo_keywords'].copy()
  elif content['tracking'].get('content_topics'):
    item['tags'] = content['tracking']['content_topics'].split(';')

  lead_image = None
  if content['promo_items']['basic']['type'] == 'image':
    lead_image = content['promo_items']['basic']
    item['_image'] = lead_image['url']

  if content['content_elements'][0]['type'] == 'image' or content['content_elements'][0]['type'] == 'video':
    lead_image = None

  item['summary'] = content['description']['basic']

  item['content_html'] = fusion.get_content_html(content, lead_image, resize_image, url, save_debug)
  return item

def get_content(url, args, save_debug=False):
  item = None
  content = None
  split_url = urlsplit(url)

  next_json = nextjs.get_next_data_json(url, save_debug, 'mobile')
  if not next_json:
    return None

  content = next_json['props']['pageProps']['globalContent']
  if save_debug:
    with open('./debug/debug.json', 'w') as file:
      json.dump(content, file, indent=4)

  return get_item(content, url, args, save_debug)

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)