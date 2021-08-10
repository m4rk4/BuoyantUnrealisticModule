import json

from feedhandlers import cne
import utils

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
  return cne.get_content(url, args, save_debug)

def get_feed(args, save_debug=False):
  api_url = 'https://www.vanityfair.com/api/search?page=1&size=10&sort=date%20desc&types=article%2Cgallery%2Cvideo'
  articles = utils.get_url_json(api_url)
  if not articles:
    return None
  if save_debug:
    with open('./debug/feed.json', 'w') as file:
      json.dump(articles, file, indent=4)

  n = 0
  items = []
  for article in articles['hits']['hits']:
    url = 'https://www.vanityfair.com/' + article['_source']['_embedded']['publishHistory']['uri']
    #url = article['_source']['_embedded']['hreflang']['canonicalUrl']
    if not args['url'] in url:
      if save_debug:
        logger.debug('skipping ' + url)
      continue
    if save_debug:
      logger.debug('getting content for ' + url)
    item = cne.get_content(url, args, save_debug)
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