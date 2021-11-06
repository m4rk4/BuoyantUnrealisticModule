import utils
from feedhandlers import clay

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
  return clay.get_content(url, args, save_debug)

def get_feed(args, save_debug=False):
  feed = utils.init_jsonfeed(args)
  feed_items = None
  feed_json = utils.get_url_json('https://nymag.com/_components/nymag-latest-feed/instances/index@published')
  if feed_json:
    for site in feed_json['tabs']:
      if site['moreUrl'] in args['url']:
        feed_items = site['articles']
  if feed_items:
    n = 0
    items = []
    for feed_item in feed_items:
      if feed_item.get('type') and feed_item['type'] == 'external':
        continue
      url = feed_item['canonicalUrl'].replace('http://', 'https://')
      if save_debug:
        logger.debug('getting content for ' + url)
      item = clay.get_content(url, args, save_debug, feed_item['pageUri'])
      if item:
        if utils.filter_item(item, args) == True:
          items.append(item)
          n += 1
          if 'max' in args:
            if n == int(args['max']):
              break
    feed['items'] = items.copy()
  return feed