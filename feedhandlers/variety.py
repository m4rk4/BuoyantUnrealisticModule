import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urlsplit

from feedhandlers import rss, wp_posts
import utils

import logging
logger = logging.getLogger(__name__)

def get_gallery_content(url, args, save_debug=False):
  article_html = utils.get_url_html(url)
  if not article_html:
    return None

  m = re.search(r'https:\/\/variety\.com\/wp-json\/wp\/v2\/[^\/]+\/(\d+)', article_html)
  if not m:
    logger.warning('unable to determine wp-json url in ' + url)
    return None

  post = utils.get_url_json(m.group(0))
  if not post:
    return None

  item = wp_posts.get_post_content(post, args, save_debug)
  if not item:
    return None

  m = re.search(r'pmcGalleryExports = (\{.*\});\s?<\/script>', article_html)
  if not m:
    logger.warning('unable to extract pmcGalleryExports from ' + url)
    return item

  gallery_json = json.loads(m.group(1))
  if save_debug:
    utils.write_file(gallery_json, './debug/gallery.json')

  content_html = re.sub(r'<div id="pmc-gallery-vertical">.*', '', item['content_html'])

  if '/lists/' in url:
    for gallery in gallery_json['gallery']:
      content_html += '<hr/><h3>{}</h3>'.format(gallery['title'])
      if gallery.get('image_credit') and gallery['image_credit'] != 'null':
        caption = gallery['image_credit']
      else:
        caption = ''
      content_html += utils.add_image(gallery['image'], caption)
      content_html += gallery['description']
  else:
    for gallery in gallery_json['gallery']:
      content_html += '<hr/><h3>{}</h3>{}'.format(gallery['title'], gallery['caption'])
      if gallery.get('image_credit') and gallery['image_credit'] != 'null':
        caption = gallery['image_credit']
      else:
        caption = ''
      content_html += utils.add_image(gallery['image'], caption)

  item['content_html'] = content_html
  return item

def get_content(url, args, save_debug=False):
  # https://variety.com/2021/digital/news/youtube-bans-vaccine-misinformation-conspiracy-theories-1235076916/
  split_url = urlsplit(url)
  if '/lists/' in split_url.path or '/gallery/' in split_url.path:
    return get_gallery_content(url, args, save_debug)

  m = re.search(r'-(\d+)\/?$', split_url.path)
  if not m:
    logger.warning('unknown post id in ' + url)
    return None

  post = utils.get_url_json('https://variety.com/wp-json/wp/v2/posts/' + m.group(1))
  if not post:
    return None

  return wp_posts.get_post_content(post, args, save_debug)


def get_feed(args, save_debug=False):
  # https://variety.com/v/digital/feed/
  return rss.get_feed(args, save_debug, get_content)