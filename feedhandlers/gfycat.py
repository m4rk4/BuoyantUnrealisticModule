import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
  split_url = urlsplit(url)
  if not split_url.path.startswith('/ifr/'):
    split_path = re.split(r'\/|-', split_url.path)
    ifr_url = 'https://gfycat.com/ifr/' + split_path[1]
  else:
    ifr_url = 'https://gfycat.com' + split_url.path

  url_html = utils.get_url_html(ifr_url)
  if not url_html:
    return None

  soup = BeautifulSoup(url_html, 'html.parser')
  el = soup.find('script', attrs={"type": "application/ld+json"})
  if el:
    try:
      ld_json = json.loads(el.string)
    except:
      logger.warning('invalid ld+json in ' + ifr_url)
      ld_json = None
  else:
    logger.warning('unable to find ld+json in ' + ifr_url)

  if ld_json:
    if save_debug:
      utils.write_file(ld_json, './debug/gfycat.json')

    item = {}
    item['id'] = ld_json['url']
    item['url'] = ld_json['url']
    item['title'] = ld_json['headline']

    dt = datetime.fromisoformat(ld_json['datePublished'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    item['author'] = {}
    item['author']['name'] = ld_json['author']

    if ld_json.get('keywords'):
      item['tags'] = ld_json['keywords'].split(',')

    item['_image'] = ld_json['image']['contentUrl']
    width = ld_json['image']['width']
    height = ld_json['image']['height']

    item['_video'] = ld_json['video']['contentUrl']

    if ld_json.get('description'):
      item['summary'] = ld_json['description']
  else:
    item = {}
    item['id'] = url
    item['url'] = url
    item['title'] = soup.title.string

    el = soup.find('meta', attrs={"name": "author"})
    if el:
      item['author'] = {}
      item['author']['name'] = el['content']

    el = soup.find('meta', attrs={"name": "keywords"})
    if el and el.get('content'):
      item['tags'] = [x.strip() for x in el['content'].split(',')]

    el = soup.find('meta', attrs={"property": "og:image"})
    if el:
      item['_image'] = el['content']
      width = int(soup.find('meta', attrs={"property": "og:image:width"})['content'])
      height = int(soup.find('meta', attrs={"property": "og:image:height"})['content'])

    el = soup.find('meta', attrs={"property": "og:video"})
    if el:
      item['_video'] = el['content'].replace('-mobile.mp4', '.mp4')

  m = re.search(r' GIF by ([^\s]+)$', item['title'])
  if m:
    item['title'] = item['title'].replace(m.group(0), '')
    item['author']['name'] = m.group(1)

  caption = '{} | <a href="{}">Watch on Gfycat</a>'.format(item['title'], item['url'])
  if width > 1000:
    width = ''
    height = ''
  item['content_html'] = utils.add_image(item['_image'], caption, width, height)
  return item

def get_feed(args, save_debug=False):
  return None