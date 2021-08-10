import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

from feedhandlers import rss
import utils

import logging
logger = logging.getLogger(__name__)

def get_post_content(post, args, save_debug=False):
  item = {}
  if 'guid' in post:
    if 'rendered' in post['guid']:
      item['id'] = post['guid']['rendered']
    else:
      item['id'] = post['guid']
  elif 'id' in post:
    item['id'] = post['id']
  elif 'slug' in post:
    item['id'] = post['slug']

  if 'link' in post:
    item['url'] = post['link']
  elif 'slug' in post:
    split_url = urlsplit(args['url'])
    item['url'] = '{}://{}/{}'.format(split_url.scheme, split_url.netloc, post['slug'])

  if 'rendered' in post['title']:
    item['title'] = post['title']['rendered']
  else:
    item['title'] = post['title']

  dt = None
  if 'date_gmt' in post:
    dt = datetime.fromisoformat(post['date_gmt']).replace(tzinfo=timezone.utc)
  elif 'createdAt' in post:
    dt = datetime.fromtimestamp(post['createdAt']).replace(tzinfo=timezone.utc)
  if dt:
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  dt = None
  if 'modified_gmt' in post:
    dt = datetime.fromisoformat(post['modified_gmt']).replace(tzinfo=timezone.utc)
  elif 'publishedAt' in post:
    dt = datetime.fromtimestamp(post['publishedAt']).replace(tzinfo=timezone.utc)
  if dt:
    item['date_modified'] = dt.isoformat()

  # Check age
  if args.get('age'):
    if not utils.check_age(item, args):
      return None

  if 'custom_fields' in post:
    if 'authors' in post['custom_fields']:
      item['author'] = {}
      for author in post['custom_fields']['authors']:
        if item['author'].get('name'):
          item['author']['name'] += ', {}'.format(author['name'])
        else:
          item['author']['name'] = author['name']
      item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', item['author']['name'])

    if 'embedded_terms' in post['custom_fields']:
      item['tags'] = []
      if 'category' in post['custom_fields']['embedded_terms']:
        for tag in post['custom_fields']['embedded_terms']['category']:
          item['tags'].append(tag['name'])
      if 'post_tag' in post['custom_fields']['embedded_terms']:
        for tag in post['custom_fields']['embedded_terms']['post_tag']:
          item['tags'].append(tag['name'])

    if 'featured_image_url' in post['custom_fields']:
      item['image'] = post['custom_fields']['featured_image_url']
  else:
    if 'profile' in post:
      item['author'] = {}
      item['author']['name'] = post['profile']['displayName']

    if 'tags' in post:
      item['tags'] = post['tags'].copy()

    if 'mainImage' in post:
      item['image'] = post['mainImage']

  if 'excerpt' in post:
    if 'rendered' in post['excerpt']:
      item['summary'] = post['excerpt']['rendered']
    else:
      item['summary'] = post['excerpt']

  content_html = ''
  if ('addledeimage' in args or 'ledeimage' in args) and item.get('image'):
    content_html += utils.add_image(item['image'])
    # Remove image since Inoreader dispays again it if present
    del item['image']

  if 'removeimage' in args and item.get('image'):
    del item['image']

  if 'content' in post:
    content_html += post['content']['rendered']
  elif 'markup' in post:
    soup = BeautifulSoup(post['markup'], 'html.parser')
    for el in soup.find_all('div', class_='paragraph'):
      el.name = 'p'
    content_html += str(soup)

  item['content_html'] = content_html
  return item

def get_next_data_json(url, save_debug=False, user_agent='desktop'):
  url_html = utils.get_url_html(url, user_agent)
  if not url_html:
    return None
  if save_debug:
    with open('./debug/debug.html', 'w', encoding='utf-8') as f:
      f.write(url_html)

  soup = BeautifulSoup(url_html, 'html.parser')
  next_data = soup.find('script', id='__NEXT_DATA__')
  if not next_data:
    logger.warning('no NEXT_DATA found in ' + url)
    return None

  try:
    next_json = json.loads(str(next_data.contents[0]))
  except:
    logger.warning('error converting NEXT_DATA to json in ' + url)
    return None
  if save_debug:
    with open('./debug/debug.json', 'w') as file:
      json.dump(next_json, file, indent=4)
  return next_json

def get_content(url, args, save_debug=False):
  next_json = get_next_data_json(url, save_debug)
  if not next_json:
    return None

  if 'data' in next_json['props']['pageProps']:
    item = get_post_content(next_json['props']['pageProps']['data'], args, save_debug)
  elif 'post' in next_json['props']['pageProps']:
    item = get_post_content(next_json['props']['pageProps']['post'], args, save_debug)
  else:
    logger.warning('unknown NEXT_DATA post format in ' + url)
    return None

  return item

def get_feed(args, save_debug=False):
  if re.search(r'\/rss|\/feed', args['url']):
    n = 0
    items = []
    feed = rss.get_feed(args, save_debug)
    for feed_item in feed['items']:
      item = get_content(feed_item['url'], args)
      if utils.filter_item(item, args) == True:
        items.append(item)
        n += 1
        if 'max' in args and n == int(args['max']):
          break
    feed['items'] = items.copy()

  else:
    feed = utils.init_jsonfeed(args)
    html = utils.get_url_html(args['url'])
    if html:
      soup = BeautifulSoup(html, 'html.parser')
      next_data = soup.find('script', id='__NEXT_DATA__')
      if next_data:
        next_json = json.loads(next_data.string)
        if save_debug:
          with open('./debug/debug.json', 'w') as file:
            json.dump(next_json, file, indent=4)

        # Make a list of all the posts
        posts = []
        if 'data' in next_json['props']['pageProps']:
          next_posts = next_json['props']['pageProps']['data']
        else:
          next_posts = next_json['props']['pageProps']
        for key, val in next_posts.items():
          if key == 'featuredCollections' or key == 'namespacesRequired':
            continue
          if key == 'curatedTagsStories':
            for tag_stories in val:
              posts += tag_stories['stories']
          else:
            posts += val
        if save_debug and False:
          with open('./debug/debug.json', 'w') as file:
            json.dump(posts, file, indent=4)

        # Sort by date
        try:
          posts = sorted(posts, key = lambda k: datetime.fromisoformat(k['date']).timestamp(), reverse = True)
        except:
          posts = sorted(posts, key = lambda k: k['createdAt'], reverse = True)
        if save_debug and False:
          with open('./debug/debug.json', 'w') as file:
            json.dump(posts, file, indent=4)

        for post in posts:
          item = get_post_content(post, args)
          if utils.filter_item(item, args) == True:
            feed['items'].append(item)
  return feed
