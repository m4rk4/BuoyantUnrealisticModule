import feedparser
from datetime import datetime, timezone

import utils

import logging
logger = logging.getLogger(__name__)

def get_feed(args, save_debug=False, func_get_content=None):
  if args.get('rss'):
    rss_url = args['rss']
  elif args.get('fromrss'):
    rss_url = args['fromrss']
  else:
    rss_url = args['url']

  rss_feed = utils.get_url_html(rss_url)
  if not rss_url:
    return None
  
  try:
    d = feedparser.parse(rss_feed)
  except:
    logger.warning('Feedparser error ' + rss_url)
    return None

  if save_debug:
    utils.write_file(str(d), './debug/feed.txt')

  feed = utils.init_jsonfeed(args)

  if 'title' in d.feed:
    feed['title'] = d.feed.title
  if 'link' in d.feed:
    feed['home_page_url'] = d.feed.link
  if 'title_detail' in d.feed:
    feed['feed_url'] = d.feed.title_detail.base
  if 'image' in d.feed:
    feed['favicon'] = d.feed.image.href

  feed_items = []
  for entry in d.entries:
    item = {}

    if 'feedburner_origlink' in entry:
      entry_link = entry.feedburner_origlink
    else:
      entry_link = entry.link
    if not 'youtube' in entry_link:
      entry_link = utils.clean_url(entry_link)

    if 'guid' in entry:
      entry_id = entry.guid
    elif 'id' in entry:
      entry_id = entry.id
    else:
      entry_id = entry_link
 
    # Skip duplicates based on the id
    if len(feed_items) > 0:
      if any(it['id'] == entry_id for it in feed_items):
        logger.debug('skipping duplicate ' + entry_id)
        continue

    item['id'] = entry_id
    item['url'] = entry_link
    item['title'] = entry.title

    if 'author_detail' in entry:
      item['author'] = entry.author_detail
    elif 'author' in entry:
      item['author'] = {}
      item['author']['name'] = entry.author

    ts = None
    if 'published_parsed' in entry:
      ts = entry.published_parsed
    elif 'updated_parsed' in entry:
      ts = entry.updated_parsed
    if ts:
      dt = datetime(*ts[0:7]).replace(tzinfo=timezone.utc)
      item['date_published'] = dt.isoformat()
      item['_timestamp'] = dt.timestamp()
      item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    # Check age
    if args.get('age'):
      if not utils.check_age(item, args):
        continue

    if 'tags' in entry:
      item['tags'] = []
      for tag in entry.tags:
        item['tags'].append(tag.term)

    if 'media_thumbnail' in entry:
      item['image'] = entry.media_thumbnail[0]['url']

    if 'summary' in entry:
      item['summary'] = entry.summary

    if 'content' in entry:
      item['content_html'] = entry.content[0]['value']

    # Check filters
    if utils.filter_item(item, args) == True:
      feed_items.append(item)

  if feed_items:
    # Sort items by date
    if feed_items[0].get('_timestamp'):
      feed_items = sorted(feed_items, key=lambda k: k.get('_timestamp', 0), reverse=True)

    # Check max # of items & trim if necessary
    if args.get('max'):
      i = int(args['max'])
      if len(feed_items) > i:
        del feed_items[i:]

    # Get content if a function is given
    if func_get_content:
      for i, it in enumerate(feed_items):
        if save_debug:
          logger.debug('getting content for ' + it['url'])
        item = func_get_content(it['url'], args, save_debug)
        if item:
          # Add anything missing (except image)
          for key, val in feed_items[i].items():
            if not key in item and key != 'image':
              item[key] = val
          feed_items[i] = item

  feed['items'] = feed_items.copy()
  return feed