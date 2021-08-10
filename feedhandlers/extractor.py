import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from html import unescape

from feedhandlers import rss
import utils

import logging
logger = logging.getLogger(__name__)

def get_content(url, args, save_debug=False):
  article_html = utils.get_url_html(url)
  if not article_html:
    return None
  if save_debug:
    with open('./debug/debug.html', 'w', encoding='utf-8') as f:
      f.write(article_html)

  soup = BeautifulSoup(article_html, 'html.parser')

  item = {}
  item['id'] = url
  item['url'] = url

  el = soup.find('meta', attrs={"property": "og:title"})
  if el:
    item['title'] = unescape(el['content'])

  el = soup.find('meta', attrs={"name": "article:published_time"})
  if not el:
    el = soup.find('meta', attrs={"itemprop": "datePublished"})
  if el:
    if 'Z' in el['content']:
      dt = datetime.fromisoformat(el['content'].replace('Z', '+00:00'))
    else:
      dt = datetime.fromisoformat(el['content']).astimezone(tz=None)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  el = soup.find('meta', attrs={"name": "article:modified_time"})
  if not el:
    el = soup.find('meta', attrs={"itemprop": "dateModified"})
  if el:
    if 'Z' in el['content']:
      dt = datetime.fromisoformat(el['content'].replace('Z', '+00:00'))
    else:
      dt = datetime.fromisoformat(el['content']).astimezone(tz=None)
    item['date_modified'] = dt.isoformat()

  el = soup.find('meta', attrs={"name": "author"})
  if el:
    item['author'] = {}
    item['author']['name'] = el['content'].replace('By ', '')
  else:
    el = soup.find('div', attrs={"itemtype": "https://schema.org/Person"})
    if el:
      item['author'] = {}
      item['author']['name'] = el.meta['content']

  el = soup.find('meta', attrs={"name": "keywords"})
  if el:
    item['tags'] = [tag.strip() for tag in el['content'].split(',')]

  el = soup.find('meta', attrs={"property": "og:image"})
  if el:
    item['_image'] = el['content']

  el = soup.find('meta', attrs={"name": "description"})
  if el:
    item['summary'] = el['content']

  article_body = soup.find(id='articlebody')
  if not article_body:
    article_body = soup.find(class_='articlebody')

  if article_body:
    # Specific to thehackernews.com
    el = article_body(class_='stophere')
    if el:
      for it in reversed(article_body.contents):
        if it.name:
          if it.get('class') and 'stophere' in it['class']:
            break
          it.decompose()
    for el in article_body.find_all(class_='separator'):
      img = el.find('img')
      if img:
        new_el = BeautifulSoup(utils.add_image(img['src']), 'html.parser')
        el.insert_after(new_el)
        el.decompose()
    for el in article_body.find_all('table', class_='tr-caption-container'):
      img = el.find('img')
      if img:
        new_el = BeautifulSoup(utils.add_image(img['src'], el.get_text()), 'html.parser')
        el.insert_after(new_el)
        el.decompose()
    
    for el in article_body.find_all(class_=re.compile(r'ad_')):
      el.decompose()

    for el in article_body.find_all(re.compile(r'aside|script')):
      el.decompose()

    item['content_html'] = str(article_body)
  else:
    if item.get('summary'):
      item['content_html'] = item['summary']
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)