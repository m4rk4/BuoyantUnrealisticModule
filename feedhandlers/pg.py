import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)

def resize_image(image, width=1000):
  if image.get('cdn'):
    sizes = []
    for size in image['cdn']['sizes']:
      if not re.search(r'cTC|cMC', size, flags=re.I):
        m = re.search(r'^(\d+)x', size)
        if m:
          s = {"width": int(m.group(1)), "size": size}
          sizes.append(s)
    size = utils.closest_dict(sizes, 'width', width)
    img_src = 'https://{}/{}/{}'.format(image['cdn']['host'], size['size'], image['cdn']['fileName'])
  else:
    size = image['url'].split('/')[-2]
    img_src = image['url'].replace(size, '{}x'.format(width))
  return img_src

def add_image(image):
  captions = []
  if image.get('caption'):
    captions.append(image['caption'])
  if image.get('photoCredit'):
    captions.append(image['photoCredit'])
  return utils.add_image(resize_image(image), ' | '.join(captions))

def get_content(url, args, save_debug=False):
  split_url = urlsplit(url)
  m = re.search(r'\/(\d+)$', split_url.path)
  if not m:
    logger.warning('unable to parse article id in ' + url)
    return None

  article_json = utils.get_url_json('https://api2.post-gazette.com/top/2/article/{}/'.format(m.group(1)))
  if not article_json:
    return None
  if save_debug:
    utils.write_file(article_json, './debug/debug.json')

  article = article_json['articles'][0]
  item = {}
  item['id'] = article['storyID']
  item['url'] = article['link']
  item['title'] = article['title']

  dt = datetime.strptime(article['pubDate'], '%a, %d %b %Y %H:%M:%S %z').astimezone(timezone.utc)
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = utils.format_display_date(dt)
  dt = datetime.strptime(article['contentModified'], '%a, %d %b %Y %H:%M:%S %z').astimezone(timezone.utc)
  item['date_modified'] = dt.isoformat()

  item['author'] = {}
  item['author']['name'] = re.sub(r'^By ', '', article['author'])

  item['_image'] = resize_image(article['images'][0])

  article_images = article['images'].copy()

  item['content_html'] = add_image(article_images[0])
  del article_images[0]

  soup = BeautifulSoup(article['body'], 'html.parser')

  for el in soup.find_all(class_='pg-embedcode-largeimage'):
    new_html = ''
    title = el.img['src'].split('/')[-1]
    for i, image in enumerate(article_images):
      if image['title'] == title:
        new_html = add_image(image)
        del article_images[i]
        break
    if new_html:
      new_el = BeautifulSoup(new_html, 'html.parser')
      el.insert_after(new_el)
      el.decompose()

  for el in soup.find_all('blockquote', class_='twitter-tweet'):
    tweet_url = el.find_all('a')
    m = re.search(r'https:\/\/twitter\.com/[^\/]+\/status\/\d+', tweet_url[-1]['href'])
    if m:
      new_html = utils.add_twitter(m.group(0))
      new_el = BeautifulSoup(new_html, 'html.parser')
      el.insert_after(new_el)
      el.decompose()

  item['content_html'] += str(soup)

  if article_images:
    for image in article_images:
      item['content_html'] += add_image(image)

  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)